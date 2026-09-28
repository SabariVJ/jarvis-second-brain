from __future__ import annotations

import os
import subprocess
import time
from typing import Iterable, Optional

import psutil
import uiautomation as auto

try:
    import pyperclip
except Exception:  # optional fallback only
    pyperclip = None


_WHATSAPP_PROCESS_HINTS = ("whatsapp",)
_SEARCH_NAME_HINTS = (
    "search",
    "search or start a new chat",
    "find a chat",
    "search chats",
)


def _log(player, text: str) -> None:
    print(f"[WhatsApp Desktop] {text}")
    if player:
        try:
            player.write_log(f"[whatsapp] {text[:80]}")
        except Exception:
            pass


def _process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name() or ""
    except Exception:
        return ""


def _whatsapp_windows() -> list:
    """Return visible top-level windows that belong to WhatsApp Desktop."""
    matches = []
    try:
        root = auto.GetRootControl()
        for win in root.GetChildren():
            try:
                name = (win.Name or "").strip()
                proc = _process_name(win.ProcessId).strip()
                hay = f"{name} {proc}".casefold()
                if any(hint in hay for hint in _WHATSAPP_PROCESS_HINTS):
                    matches.append(win)
            except Exception:
                continue
    except Exception:
        pass
    return matches


def _find_whatsapp_window(timeout: float = 3.0):
    end = time.time() + timeout
    while time.time() < end:
        wins = _whatsapp_windows()
        if wins:
            # Prefer the main window rather than transient dialogs/call popups.
            wins.sort(
                key=lambda w: (
                    0 if (w.Name or "").strip().casefold() == "whatsapp" else 1,
                    -_rect_area(getattr(w, "BoundingRectangle", None)),
                )
            )
            return wins[0]
        time.sleep(0.25)
    return None


def _rect_area(rect) -> int:
    try:
        return max(0, int(rect.right - rect.left)) * max(0, int(rect.bottom - rect.top))
    except Exception:
        return 0


def _launch_whatsapp() -> tuple[bool, str]:
    """Launch the installed WhatsApp Desktop app without falling back to WhatsApp Web."""
    if _find_whatsapp_window(0.5):
        return True, "WhatsApp Desktop is already running."

    errors: list[str] = []

    # Preferred: WhatsApp's registered URI protocol.
    try:
        if os.name == "nt":
            os.startfile("whatsapp:")
        else:
            raise OSError("WhatsApp Desktop launcher is implemented for Windows only")
        if _find_whatsapp_window(8):
            return True, "WhatsApp Desktop launched."
    except Exception as e:
        errors.append(f"URI launch: {e}")

    # Microsoft Store / Start Apps fallback. This avoids hard-coding the package family.
    try:
        cmd = (
            "Get-StartApps | Where-Object { $_.Name -like '*WhatsApp*' } | "
            "Select-Object -First 1 -ExpandProperty AppID"
        )
        app_id = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=8,
        ).stdout.strip()
        if app_id:
            subprocess.Popen(
                ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if _find_whatsapp_window(10):
                return True, "WhatsApp Desktop launched."
        else:
            errors.append("WhatsApp was not found in Get-StartApps")
    except Exception as e:
        errors.append(f"StartApps launch: {e}")

    return False, "Could not launch WhatsApp Desktop. " + "; ".join(errors[-2:])


def _activate(win) -> None:
    try:
        win.SetActive()
    except Exception:
        pass
    try:
        win.SetFocus()
    except Exception:
        pass
    time.sleep(0.35)


def _walk(root, max_depth: int = 12) -> Iterable:
    try:
        for ctl, _depth in auto.WalkControl(root, maxDepth=max_depth):
            yield ctl
    except Exception:
        return


def _is_visible_enabled(ctl) -> bool:
    try:
        return bool(ctl.IsEnabled) and not bool(ctl.IsOffscreen)
    except Exception:
        return True


def _control_name(ctl) -> str:
    try:
        return (ctl.Name or "").strip()
    except Exception:
        return ""


def _control_type(ctl) -> str:
    try:
        return ctl.ControlTypeName or ""
    except Exception:
        return ""


def _set_text(control, text: str) -> bool:
    """Set a WinUI/UIA text box without using pyautogui."""
    try:
        control.SetFocus()
    except Exception:
        pass
    try:
        control.Click()
    except Exception:
        pass

    try:
        control.GetValuePattern().SetValue(text)
        return True
    except Exception:
        pass

    try:
        control.SendKeys("{Ctrl}a{Backspace}")
        if pyperclip is not None:
            pyperclip.copy(text)
            control.SendKeys("{Ctrl}v")
        else:
            control.SendKeys(text)
        return True
    except Exception:
        return False


def _find_search_box(win):
    edits = []
    for ctl in _walk(win, 10):
        if not _is_visible_enabled(ctl):
            continue
        ctype = _control_type(ctl).casefold()
        name = _control_name(ctl).casefold()
        if "edit" not in ctype and "document" not in ctype:
            continue
        score = 0
        if "search" in name:
            score += 20
        if "chat" in name:
            score += 8
        if any(h in name for h in _SEARCH_NAME_HINTS):
            score += 30
        edits.append((score, ctl))

    if edits:
        edits.sort(key=lambda item: item[0], reverse=True)
        if edits[0][0] > 0:
            return edits[0][1]

    # WhatsApp Desktop supports Ctrl+F in current builds. Use it only as a fallback,
    # then inspect whichever edit control gained focus.
    try:
        _activate(win)
        auto.SendKeys("{Ctrl}f")
        time.sleep(0.4)
        focused = auto.GetFocusedControl()
        if focused and _is_visible_enabled(focused):
            return focused
    except Exception:
        pass

    return None


def _click_control(ctl) -> bool:
    try:
        ctl.SetFocus()
    except Exception:
        pass
    try:
        ctl.Click()
        return True
    except Exception:
        pass
    try:
        ctl.GetInvokePattern().Invoke()
        return True
    except Exception:
        return False


def _find_contact_result(win, contact_name: str):
    wanted = " ".join(contact_name.casefold().split())
    exact = []
    fuzzy = []

    for ctl in _walk(win, 12):
        if not _is_visible_enabled(ctl):
            continue
        name = _control_name(ctl)
        if not name:
            continue
        norm = " ".join(name.casefold().split())
        ctype = _control_type(ctl).casefold()

        # Avoid selecting the search edit itself.
        if "edit" in ctype or "document" in ctype:
            continue

        if norm == wanted:
            exact.append(ctl)
        elif wanted and wanted in norm:
            # Keep a conservative fallback. Shorter accessible names are more likely
            # to be the actual search result than large container descriptions.
            fuzzy.append((len(norm), ctl))

    if exact:
        return exact[0]
    if fuzzy:
        fuzzy.sort(key=lambda item: item[0])
        # Only accept a unique shortest match; this reduces wrong-contact calls.
        shortest = fuzzy[0][0]
        tied = [ctl for length, ctl in fuzzy if length == shortest]
        if len(tied) == 1:
            return tied[0]
    return None


def _find_call_button(win, intent: str):
    want_video = intent == "video_call"
    ranked = []

    for ctl in _walk(win, 12):
        if not _is_visible_enabled(ctl):
            continue
        name = _control_name(ctl)
        if not name:
            continue
        norm = name.casefold()
        ctype = _control_type(ctl).casefold()
        if "button" not in ctype and "hyperlink" not in ctype:
            continue

        score = 0
        if want_video:
            if "video" in norm and "call" in norm:
                score += 100
            elif norm in ("video", "camera"):
                score += 60
        else:
            if "video" in norm:
                continue
            if "voice call" in norm:
                score += 120
            elif "audio call" in norm:
                score += 110
            elif norm in ("call", "voice call", "audio call"):
                score += 100
            elif "call" in norm:
                score += 50

        if score:
            ranked.append((score, ctl))

    if ranked:
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1]
    return None


def _verify_call_started(contact_name: str, timeout: float = 10.0) -> bool:
    indicators = (
        "end call",
        "hang up",
        "ringing",
        "calling",
        "connecting",
        "mute",
        "speaker",
    )
    end = time.time() + timeout
    wanted = contact_name.casefold()

    while time.time() < end:
        for win in _whatsapp_windows():
            # A separate call window may have the contact in its title.
            title = _control_name(win).casefold()
            if wanted and wanted in title and title != "whatsapp":
                return True
            for ctl in _walk(win, 8):
                name = _control_name(ctl).casefold()
                if any(indicator in name for indicator in indicators):
                    return True
        time.sleep(0.4)
    return False


def whatsapp_desktop_call(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Start a WhatsApp Desktop voice/video call to an exact saved contact.

    This intentionally does NOT fall back to WhatsApp Web. It returns success only
    after the call UI can be verified; otherwise it reports the exact failed stage.
    """
    params = parameters or {}
    contact = str(
        params.get("contact_name")
        or params.get("contact")
        or params.get("receiver")
        or ""
    ).strip()
    intent = str(params.get("intent") or "voice_call").strip().casefold()
    if intent not in ("voice_call", "video_call"):
        intent = "voice_call"

    if not contact:
        return "Please provide the exact saved WhatsApp contact name."
    if os.name != "nt":
        return "WhatsApp Desktop calling is currently implemented for Windows only."

    ok, launch_msg = _launch_whatsapp()
    _log(player, launch_msg)
    if not ok:
        return launch_msg

    win = _find_whatsapp_window(5)
    if not win:
        return "WhatsApp Desktop opened, but its main window could not be detected."

    _activate(win)

    search = _find_search_box(win)
    if not search:
        return "WhatsApp Desktop is open, but JARVIS could not find its chat search box."
    if not _set_text(search, contact):
        return "JARVIS found WhatsApp search but could not type the contact name."

    time.sleep(1.3)
    win = _find_whatsapp_window(2) or win
    result = _find_contact_result(win, contact)
    if not result:
        return (
            f"Could not find an exact WhatsApp Desktop contact for '{contact}'. "
            "Use the contact name exactly as it is saved in WhatsApp."
        )
    if not _click_control(result):
        return f"Found '{contact}' in WhatsApp, but could not open the conversation."

    time.sleep(1.0)
    win = _find_whatsapp_window(2) or win
    button = _find_call_button(win, intent)
    kind = "video" if intent == "video_call" else "voice"
    if not button:
        return (
            f"Opened '{contact}' in WhatsApp Desktop, but could not find the {kind}-call button. "
            "Make sure this contact can receive WhatsApp calls and the app is up to date."
        )

    if not _click_control(button):
        return f"Found the WhatsApp {kind}-call button for '{contact}', but clicking it failed."

    if _verify_call_started(contact, timeout=10):
        return f"WhatsApp {kind} call started with {contact}."

    return (
        f"Clicked the WhatsApp {kind}-call button for {contact}, but could not verify that the call started. "
        "Check WhatsApp for a permission prompt or call error."
    )
