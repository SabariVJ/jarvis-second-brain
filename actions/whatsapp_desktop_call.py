from __future__ import annotations

import os
import subprocess
import threading
from contextlib import nullcontext, contextmanager
import time
from typing import Iterable, Optional

import psutil
import uiautomation as auto
from actions import _whatsapp_semantics as semantics

try:
    import pyperclip
except Exception:  # optional fallback only
    pyperclip = None


_WHATSAPP_PROCESS_HINTS = ("whatsapp", "whatsapp.exe")
_WHATSAPP_WINDOW_TITLES = ("whatsapp",)
_SEARCH_NAME_HINTS = (
    "search",
    "search or start a new chat",
    "find a chat",
    "search chats",
)
_CALL_LOCK = threading.Lock()


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


def _whatsapp_pids() -> set[int]:
    """Return running WhatsApp Desktop process IDs.

    Microsoft Store WhatsApp currently exposes a real `WhatsApp.exe` process.
    Detect it directly with psutil instead of relying only on UI Automation.
    """
    pids: set[int] = set()
    try:
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                name = str(proc.info.get("name") or "").casefold()
                exe = str(proc.info.get("exe") or "").casefold()
                if name in ("whatsapp.exe", "whatsapp.root.exe", "whatsapp"):
                    pids.add(int(proc.info["pid"]))
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, TypeError, ValueError):
                continue
    except Exception:
        pass
    return pids


def _rect_area(rect) -> int:
    try:
        return max(0, int(rect.right - rect.left)) * max(0, int(rect.bottom - rect.top))
    except Exception:
        return 0


def _control_from_hwnd(hwnd: int):
    try:
        ctl = auto.ControlFromHandle(hwnd)
        if ctl:
            return ctl
    except Exception:
        pass
    return None


def _native_whatsapp_windows() -> list:
    """Find WhatsApp windows with Win32 as a fallback when UIA enumeration misses them."""
    if os.name != "nt":
        return []

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        pids = _whatsapp_pids()
        found: list = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True

                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, len(buf))
                title = (buf.value or "").strip()

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                pid_value = int(pid.value)

                if pid_value in pids:
                    ctl = _control_from_hwnd(int(hwnd))
                    if ctl is not None:
                        found.append(ctl)
            except Exception:
                pass
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        return found
    except Exception:
        return []


def _whatsapp_windows() -> list:
    """Return visible top-level windows belonging to WhatsApp Desktop.

    This intentionally uses three signals because Store/WinUI builds sometimes
    expose inconsistent process metadata through UI Automation:
      1. actual WhatsApp.exe PIDs from psutil,
      2. top-level title/process matching through UIA,
      3. native Win32 EnumWindows fallback.
    """
    matches = []
    pids = _whatsapp_pids()

    try:
        root = auto.GetRootControl()
        for win in root.GetChildren():
            try:
                name = (win.Name or "").strip()
                proc = _process_name(int(win.ProcessId)).strip()
                hay = f"{name} {proc}".casefold()
                if int(win.ProcessId) in pids:
                    matches.append(win)
            except Exception:
                continue
    except Exception:
        pass

    # Direct UIA title lookup is useful for the WinUI Store build.
    for kwargs in (
        {"searchDepth": 1, "ClassName": "WinUIDesktopWin32WindowClass", "Name": "WhatsApp"},
        {"searchDepth": 1, "Name": "WhatsApp"},
    ):
        try:
            win = auto.WindowControl(**kwargs)
            if win.Exists(0.5, 0.1) and int(win.ProcessId) in pids:
                matches.append(win)
        except Exception:
            pass

    matches.extend(_native_whatsapp_windows())

    # Deduplicate by native handle when available, otherwise by PID/title.
    unique = []
    seen = set()
    for win in matches:
        try:
            handle = int(getattr(win, "NativeWindowHandle", 0) or 0)
            key = ("hwnd", handle) if handle else (
                "uia",
                int(getattr(win, "ProcessId", 0) or 0),
                (getattr(win, "Name", "") or "").strip().casefold(),
            )
        except Exception:
            key = ("obj", id(win))
        if key not in seen:
            seen.add(key)
            unique.append(win)
    return unique


def _find_whatsapp_window(timeout: float = 3.0):
    end = time.time() + max(0.0, timeout)
    while True:
        wins = _whatsapp_windows()
        if wins:
            # Prefer the actual main window, then the largest WhatsApp window.
            wins.sort(
                key=lambda w: (
                    0 if (getattr(w, "Name", "") or "").strip().casefold() == "whatsapp" else 1,
                    -_rect_area(getattr(w, "BoundingRectangle", None)),
                )
            )
            return wins[0]
        if time.time() >= end:
            return None
        time.sleep(0.2)


def _launch_with_start_apps() -> tuple[bool, str]:
    """Launch the Store/Start-menu WhatsApp app without pyautogui."""
    try:
        cmd = (
            "$app = Get-StartApps | Where-Object { $_.Name -like '*WhatsApp*' } | Select-Object -First 1; "
            "if ($app) { $app.AppID }"
        )
        app_id = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=8,
        ).stdout.strip()
        if not app_id:
            return False, "WhatsApp was not found in Windows Start Apps."

        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True, f"Launched WhatsApp via Start Apps ({app_id})."
    except Exception as e:
        return False, f"Start Apps launch failed: {e}"


def _launch_whatsapp() -> tuple[bool, str]:
    """Detect or launch WhatsApp Desktop; never fall back to WhatsApp Web."""
    # The user's Store build exposes ProcessName `WhatsApp` and window title `WhatsApp`.
    # Check the process independently from UIA so a UIA miss is not misreported as
    # "WhatsApp Desktop is not running".
    pids = _whatsapp_pids()
    win = _find_whatsapp_window(1.0)
    if win:
        return True, f"WhatsApp Desktop detected (PID {getattr(win, 'ProcessId', 'unknown')})."

    errors: list[str] = []

    if pids:
        # Process exists but the window is hidden/minimized/not yet exposed to UIA.
        ok, msg = _launch_with_start_apps()
        errors.append(f"process detected ({sorted(pids)}); {msg}")
        if ok and _find_whatsapp_window(8):
            return True, "WhatsApp Desktop process was running and its window is now available."

    # WhatsApp's registered URI protocol is fast on current Store builds.
    try:
        os.startfile("whatsapp:")
        if _find_whatsapp_window(8):
            return True, "WhatsApp Desktop launched."
    except Exception as e:
        errors.append(f"URI launch: {e}")

    ok, msg = _launch_with_start_apps()
    if ok and _find_whatsapp_window(10):
        return True, "WhatsApp Desktop launched."
    errors.append(msg)

    pids_after = _whatsapp_pids()
    if pids_after:
        return False, (
            "WhatsApp.exe is running, but Windows UI Automation cannot access its main window. "
            "Open WhatsApp Desktop so its main chat window is visible, then try again. "
            f"Detected PID(s): {sorted(pids_after)}."
        )

    return False, "Could not launch WhatsApp Desktop. " + "; ".join(errors[-3:])




def _walk(root, max_depth: int = 12) -> Iterable:
    # The Store WinUI/WebView host consumes ~12 levels before the web app starts.
    # uiautomation uses RawViewWalker (see its _AutomationClient implementation).
    # Legacy shallow callers must also reach the web content. Bound node count and
    # elapsed enumeration time, without treating a truncated tree as success.
    started = time.monotonic()
    try:
        for index, (ctl, _depth) in enumerate(auto.WalkControl(root, maxDepth=max(48, max_depth))):
            if index >= 6000 or time.monotonic() - started > 8:
                _log(None, "backend=UIA/raw traversal limit reached; state remains unverified")
                break
            yield ctl
    except Exception:
        return


def _is_visible_enabled(ctl) -> bool:
    try:
        return bool(ctl.IsEnabled) and not bool(ctl.IsOffscreen)
    except Exception:
        return False


def _control_name(ctl) -> str:
    return semantics.name(ctl)


def _control_type(ctl) -> str:
    try:
        return ctl.ControlTypeName or ""
    except Exception:
        return ""




def _find_search_box(win):
    matches = [ctl for ctl in _walk(win) if semantics.is_search(ctl)]
    return matches[0] if len(matches) == 1 else None




def _native_window_rect(win=None):
    """Return the physical pixel rect for the real WhatsApp top-level window.

    SetCursorPos uses physical desktop pixels. UI Automation BoundingRectangle can
    be DPI-scaled on some Windows setups, which caused clicks to land in the chat
    list instead of the search box.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = _native_hwnd_for_whatsapp()
        if not hwnd and win is not None:
            hwnd = int(getattr(win, "NativeWindowHandle", 0) or 0)
        if not hwnd:
            return None
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return hwnd, int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    except Exception:
        return None














def _native_hwnd_for_whatsapp() -> int:
    """Return the largest visible top-level HWND owned by WhatsApp.exe."""
    if os.name != "nt":
        return 0
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        pids = _whatsapp_pids()
        candidates = []
        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd, _):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if int(pid.value) not in pids:
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, len(buf))
                title = (buf.value or "").strip()
                if "whatsapp" not in title.casefold():
                    return True
                rect = wintypes.RECT()
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return True
                area = max(0, rect.right-rect.left) * max(0, rect.bottom-rect.top)
                candidates.append((area, int(hwnd)))
            except Exception:
                pass
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        if not candidates:
            return 0
        candidates.sort(reverse=True)
        return candidates[0][1]
    except Exception:
        return 0


def _force_foreground_hwnd(hwnd: int) -> bool:
    """Reliably bring a window to the foreground from a console process."""
    if not hwnd or os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)

        fg = user32.GetForegroundWindow()
        current_tid = kernel32.GetCurrentThreadId()
        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)

        attached_fg = False
        attached_target = False
        try:
            if fg_tid and fg_tid != current_tid:
                attached_fg = bool(user32.AttachThreadInput(current_tid, fg_tid, True))
            if target_tid and target_tid != current_tid:
                attached_target = bool(user32.AttachThreadInput(current_tid, target_tid, True))
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            if attached_target:
                user32.AttachThreadInput(current_tid, target_tid, False)
            if attached_fg:
                user32.AttachThreadInput(current_tid, fg_tid, False)
        time.sleep(0.35)
        return int(user32.GetForegroundWindow() or 0) == int(hwnd)
    except Exception:
        return False


def _set_clipboard_text(text: str) -> bool:
    if pyperclip is not None:
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            pass
    try:
        escaped = text.replace("'", "''")
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", f"Set-Clipboard -Value '{escaped}'"],
            capture_output=True,
            timeout=5,
            check=True,
        )
        return True
    except Exception:
        return False









def _find_contact_result(win, contact_name: str):
    candidates = []
    seen = set()
    for ctl in _walk(win):
        if not semantics.result_matches(ctl, contact_name):
            continue
        try:
            key = tuple(ctl.GetRuntimeId())
        except Exception:
            key = id(ctl)
        if key not in seen:
            seen.add(key)
            candidates.append(ctl)
    return candidates[0] if len(candidates) == 1 else None


def _find_call_button(win, intent: str, header=None):
    # Restrict actual call placement to the verified conversation header.
    root = semantics.header_container(header) if header is not None else win
    if root is None:
        return None
    buttons = [c for c in _walk(root) if semantics.is_call_button(c, intent == "video_call")]
    unique = {}
    for ctl in buttons:
        try:
            key = tuple(ctl.GetRuntimeId())
        except Exception:
            key = id(ctl)
        unique[key] = ctl
    return next(iter(unique.values())) if len(unique) == 1 else None


def _verify_call_started(contact_name: str, timeout: float = 10.0) -> bool:
    indicators = ("end call", "hang up")
    end = time.time() + timeout
    wanted = semantics.norm(contact_name)

    while time.time() < end:
        for win in _whatsapp_windows():
            root = _webview_content_root(win, None)
            for ctl in _walk(root, 8):
                name = _control_name(ctl).casefold()
                ctype = _control_type(ctl).casefold()
                if "button" in ctype and name in indicators and _is_visible_enabled(ctl):
                    if not wanted:
                        return True  # preflight: reject any existing call
                    for parent in semantics.ancestors(ctl, 16):
                        nodes = list(semantics.subtree(parent, limit=401, depth=16))
                        if len(nodes) >= 401:
                            continue
                        # Never correlate a call control with a sidebar contact
                        # or a message in the main conversation document.
                        if any(semantics.is_row(n) or _control_type(n) == "EditControl" for n in nodes):
                            continue
                        if any(_is_visible_enabled(n) and semantics.norm(_control_name(n)) == wanted for n in nodes):
                            _log(None, f"VERIFY_ACTIVE_CALL_UI verified backend=UIA/raw/MSAA contact={contact_name!r} control={name!r}")
                            return True
        time.sleep(0.4)
    return False


def _control_value(ctl) -> str:
    # WebView contenteditable search can expose an empty ValuePattern while its
    # TextPattern contains the actual editor contents.
    for read in (lambda: ctl.GetValuePattern().Value,
                 lambda: ctl.GetLegacyIAccessiblePattern().Value,
                 lambda: ctl.GetTextPattern().DocumentRange.GetText(-1)):
        try:
            value = str(read() or "")
            if value:
                return value
        except Exception:
            pass
    return ""


def _same_control(a, b) -> bool:
    if a is None or b is None:
        return False
    try:
        return a.GetRuntimeId() == b.GetRuntimeId()
    except Exception:
        return False


def _find_chat_header(win, contact_name: str):
    matches = []
    for ctl in _walk(win):
        if not _is_visible_enabled(ctl) or semantics.norm(_control_name(ctl)) != semantics.norm(contact_name):
            continue
        if semantics.header_container(ctl) is not None:
            # Use the named button, not a duplicate nested text node.
            if _control_type(ctl) == "ButtonControl":
                return ctl
            matches.append(ctl)
    return matches[0] if len(matches) == 1 else None


def _diagnose(player, win, stage: str, backend="UIA/raw", **controls) -> None:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = int(getattr(win, "NativeWindowHandle", 0) or 0)
        fg = int(user32.GetForegroundWindow() or 0)
        dpi = user32.GetDpiForWindow(hwnd) if hwnd else 0
        focused = auto.GetFocusedControl()
        rect = getattr(win, "BoundingRectangle", None)
        names = [f"{_control_type(c)}:{_control_name(c)}" for c in _walk(win, 14)
                 if _is_visible_enabled(c) and _control_name(c)][:80]
        selected = {k: f"{_control_type(v)}:{_control_name(v)}" if v else None
                    for k, v in controls.items()}
        _log(player, f"{stage} backend={backend} pid={getattr(win, 'ProcessId', 0)} hwnd={hwnd} foreground={fg} "
             f"rect={rect} dpi={dpi} focused={_control_type(focused)}:{_control_name(focused)} "
             f"controls={names} selected={selected}")
    except Exception as exc:
        _log(player, f"{stage} diagnostic error={exc}")



def _visible_button_names(win, limit: int = 12) -> list[str]:
    names: list[str] = []
    for ctl in _walk(win, 10):
        try:
            if not _is_visible_enabled(ctl):
                continue
            ctype = _control_type(ctl).casefold()
            name = _control_name(ctl).strip()
            if name and ("button" in ctype or "hyperlink" in ctype):
                names.append(name)
        except Exception:
            continue
    # preserve order while deduplicating
    out: list[str] = []
    seen = set()
    for name in names:
        k = name.casefold()
        if k not in seen:
            seen.add(k)
            out.append(name)
        if len(out) >= limit:
            break
    return out


def _process_diagnostic() -> str:
    pids = sorted(_whatsapp_pids())
    wins = _whatsapp_windows()
    window_bits = []
    for win in wins[:5]:
        try:
            window_bits.append(
                f"title={_control_name(win)!r}, pid={getattr(win, 'ProcessId', '?')}, class={getattr(win, 'ClassName', '')!r}"
            )
        except Exception:
            pass
    return f"pids={pids}; windows=[{' | '.join(window_bits)}]"


class _VerificationError(RuntimeError):
    def __init__(self, stage, detail):
        super().__init__(f"{stage} failed: {detail}")


@contextmanager
def _physical_pixel_context():
    import ctypes
    user32 = ctypes.windll.user32
    setter = getattr(user32, "SetThreadDpiAwarenessContext", None)
    previous = None
    if setter:
        setter.argtypes = [ctypes.c_void_p]
        setter.restype = ctypes.c_void_p
        previous = setter(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    try:
        yield
    finally:
        if previous:
            setter(previous)


def _foreground_is(hwnd):
    import ctypes
    from ctypes import wintypes
    get_foreground = ctypes.windll.user32.GetForegroundWindow
    get_foreground.restype = wintypes.HWND
    return int(get_foreground() or 0) == int(hwnd)


def _sendinput_chord(hwnd, *keys):
    """Native SendInput, with target focus checked immediately before insertion."""
    import ctypes
    if not _foreground_is(hwnd):
        raise _VerificationError("FOCUS_WHATSAPP", "foreground changed before native input")
    events = [auto.KeyboardInput(key, 0, 0) for key in keys]
    releases = [auto.KeyboardInput(key, 0, 2) for key in reversed(keys)]
    events.extend(releases)
    inputs = (auto.INPUT * len(events))(*events)
    sent = ctypes.windll.user32.SendInput(len(events), inputs, ctypes.sizeof(auto.INPUT))
    if sent != len(events):
        # Release modifiers if Windows accepted only part of the chord.
        cleanup = (auto.INPUT * len(releases))(*releases)
        ctypes.windll.user32.SendInput(len(releases), cleanup, ctypes.sizeof(auto.INPUT))
        raise _VerificationError("NATIVE_INPUT", f"SendInput accepted {sent}/{len(events)} events")


def _send_search_shortcut(hwnd):
    import ctypes
    # Resolve '/' using the target thread's keyboard layout instead of assuming
    # the OEM key used by an English keyboard.
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.GetKeyboardLayout.restype = wintypes.HANDLE
    user32.VkKeyScanExW.argtypes = [wintypes.WCHAR, wintypes.HANDLE]
    user32.VkKeyScanExW.restype = ctypes.c_short
    thread = user32.GetWindowThreadProcessId(hwnd, None)
    mapped = user32.VkKeyScanExW("/", user32.GetKeyboardLayout(thread))
    if mapped == -1:
        raise _VerificationError("OPEN_SEARCH_NATIVE_KEYBOARD", "keyboard layout cannot map '/' shortcut")
    modifiers = [0x11, 0x12]  # WhatsApp global Search: Ctrl+Alt+/
    if (mapped >> 8) & 1:
        modifiers.append(0x10)
    _sendinput_chord(hwnd, *modifiers, mapped & 0xff)


def _belongs_to_window(control, hwnd):
    handles = [int(semantics.prop(c, "NativeWindowHandle", 0) or 0)
               for c in [control, *semantics.ancestors(control, 64)] if c is not None]
    if hwnd in handles:
        return True
    # WinUI may omit the WebView from its UIA parent tree. Native ancestry still
    # establishes that the detached provider belongs to the real WhatsApp HWND.
    try:
        import ctypes
        from ctypes import wintypes
        get_root = ctypes.windll.user32.GetAncestor
        get_root.argtypes = [wintypes.HWND, wintypes.UINT]
        get_root.restype = wintypes.HWND
        return any(h and int(get_root(h, 2) or 0) == hwnd for h in handles)
    except Exception:
        return False


def _focused_control(root):
    focused = auto.GetFocusedControl()
    if focused is not None and _control_type(focused) not in ("PaneControl", "WindowControl"):
        return focused
    # Query focus inside the WebView provider when the top-level provider only
    # reports the hosting pane as focused.
    matches = [c for c in [root, *_walk(root)] if semantics.prop(c, "HasKeyboardFocus", False)
               and _control_type(c) not in ("PaneControl", "WindowControl", "DocumentControl", "GroupControl")]
    return matches[0] if len(matches) == 1 else focused


def _click_accessible_control(hwnd, control, player=None):
    """Last activation fallback: the live provider's bounds, never layout offsets."""
    import ctypes
    from ctypes import wintypes
    if not _foreground_is(hwnd) or not _is_visible_enabled(control):
        return False
    rect = control.BoundingRectangle
    window_rect = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
        return False
    if not (rect.right > rect.left and rect.bottom > rect.top and
            window_rect.left <= rect.left < rect.right <= window_rect.right and
            window_rect.top <= rect.top < rect.bottom <= window_rect.bottom):
        return False
    _log(player, f"activation requested backend=UIA/live-element-bounds name={_control_name(control)!r} rect={rect}; awaiting resulting state")
    return control.Click(simulateMove=False) is not False


def _focus_search(win, hwnd, search, player):
    try:
        focused = search.SetFocus()
        _log(player, f"search focus backend=UIA/SetFocus returned={focused} has_focus={semantics.prop(search, 'HasKeyboardFocus', False)}")
    except Exception as exc:
        _log(player, f"search focus backend=UIA/SetFocus failed: {exc}")
    if _same_control(_focused_control(win), search):
        return
    try:
        search.GetLegacyIAccessiblePattern().Select(1)  # SELFLAG_TAKEFOCUS
    except Exception:
        pass
    if not _same_control(_focused_control(win), search):
        _click_accessible_control(hwnd, search, player)


def _webview_content_root(win, player):
    """Cross the observed WinUI->WebView provider boundary using native HWNDs."""
    try:
        import win32gui
        hwnd = int(win.NativeWindowHandle)
        handles = []
        win32gui.EnumChildWindows(hwnd, lambda child, _: handles.append(child), None)
        candidates = [h for h in handles if win32gui.GetClassName(h) in
                      ("Chrome_WidgetWin_0", "Chrome_WidgetWin_1", "Chrome_RenderWidgetHostHWND")]
        for handle in candidates:
            root = auto.ControlFromHandle(handle)
            if any(_control_type(c) == "DocumentControl" for c in _walk(root)):
                _log(player, f"backend=Win32->UIA/raw WebView provider hwnd={handle} parent_hwnd={hwnd}")
                return root
    except Exception as exc:
        _log(player, f"backend=Win32->UIA/raw WebView probe failed: {exc}")
    return win


def _wait_value(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while True:
        result = predicate()
        if result:
            return result
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.2)


def _pywinauto_root(win, player):
    """Reacquire WebView accessibility through pywinauto's UIA client."""
    hwnd = int(win.NativeWindowHandle)
    try:
        from pywinauto import Desktop
        wrapper = Desktop(backend="uia").window(handle=hwnd).wrapper_object()
        root = auto.Control.CreateControlFromElement(wrapper.element_info.element)
        _log(player, "backend=UIA/pywinauto acquired HWND; continuing deep raw element traversal")
        return root
    except Exception as exc:
        _log(player, f"backend=UIA/pywinauto unavailable: {exc}")
        return win


def _open_verified_search(win, hwnd, player):
    _diagnose(player, win, "OPEN_SEARCH_UIA")
    search = _find_search_box(win)
    if search is not None:
        _focus_search(win, hwnd, search, player)
        focused = _focused_control(win)
        if _foreground_is(hwnd) and _same_control(focused, search) and _belongs_to_window(focused, hwnd):
            return win, search, "UIA/raw"

    before = _focused_control(win)
    _log(player, "OPEN_SEARCH_NATIVE_KEYBOARD backend=keyboard/Win32 shortcut=Ctrl+Alt+/ requested")
    _send_search_shortcut(hwnd)
    win = _webview_content_root(win, player)
    # The global search label is now available directly from the WebView even
    # when its parent WinUI provider cannot expose it.
    exposed_search = _find_search_box(win)
    if exposed_search is not None:
        _focus_search(win, hwnd, exposed_search, player)

    def focused_search():
        if not _foreground_is(hwnd):
            return None
        focused = _focused_control(win)
        changed = not _same_control(before, focused)
        if _belongs_to_window(focused, hwnd) and semantics.is_search(focused, after_shortcut=changed):
            return focused
        return None

    search = _wait_value(focused_search, timeout=3)
    backend = "keyboard/Win32->WebView UIA/raw/MSAA"
    if search is None:
        win = _pywinauto_root(win, player)
        search = _wait_value(focused_search, timeout=2)
        backend = "keyboard/Win32+UIA/pywinauto/MSAA"
    if search is None:
        _diagnose(player, win, "VERIFY_SEARCH_MODE", backend=backend)
        raise _VerificationError("VERIFY_SEARCH_MODE", "Search shortcut sent, but no focused accessible search editor could be verified; no text was pasted")
    return win, search, backend


def _enter_verified_contact(win, hwnd, search, contact, player, backend):
    if not _foreground_is(hwnd) or not _same_control(_focused_control(win), search):
        raise _VerificationError("VERIFY_SEARCH_MODE", "search lost focus before typing")
    if not _set_clipboard_text(contact):
        raise _VerificationError("ENTER_CONTACT", "clipboard could not be set")
    _sendinput_chord(hwnd, 0x11, 0x41)
    _sendinput_chord(hwnd, 0x11, 0x56)
    def correct_value():
        focused = _focused_control(win)
        return (_foreground_is(hwnd) and _same_control(focused, search)
                and semantics.norm(_control_value(focused)) == semantics.norm(contact))
    if not _wait_value(correct_value):
        _log(player, f"ENTER_CONTACT backend={backend} observed_value={_control_value(search)!r} focused={_control_name(_focused_control(win))!r} has_focus={semantics.prop(search, 'HasKeyboardFocus', False)}")
        raise _VerificationError("ENTER_CONTACT", "focused search value did not equal the exact contact name")
    _diagnose(player, win, "ENTER_CONTACT verified", backend=backend, search=search)


def _activate_verified_element(hwnd, control, player=None):
    if not _foreground_is(hwnd):
        return False
    for backend, method in (("UIA/Invoke", lambda: control.GetInvokePattern().Invoke()),
                            ("UIA/MSAA", lambda: control.GetLegacyIAccessiblePattern().DoDefaultAction())):
        try:
            if method() is not False:
                _log(player, f"activation requested backend={backend} element={_control_name(control)!r}; awaiting resulting state")
                return True
        except Exception:
            pass
    # Keyboard activation is allowed only after focus is verified on the exact
    # result/button. No first-result Enter and no blind ArrowDown sequence.
    try:
        control.SetFocus()
        focused = _focused_control(control)
        if not _same_control(focused, control):
            return _click_accessible_control(hwnd, control, player)
        _sendinput_chord(hwnd, 0x0d)
        _log(player, f"activation requested backend=keyboard/Win32 element={_control_name(control)!r}; awaiting resulting state")
        return True
    except Exception:
        return False


def _verify_direct_chat(win, hwnd, header, contact, player):
    """Open the conversation's own info panel to positively establish its type."""
    if not _activate_verified_element(hwnd, header, player):
        raise _VerificationError("VERIFY_NOT_GROUP", "cannot open verified conversation header's contact info")

    def panel():
        nodes = list(_walk(win))
        # Info marker must be a heading/text, not a menu item offering an action.
        markers = [n for n in nodes if _is_visible_enabled(n) and
                   _control_type(n) == "TextControl" and
                   semantics.norm(_control_name(n)) in ("contact info", "group info")]
        for marker in markers:
            for parent in list(semantics.ancestors(marker))[:5]:
                if _control_type(parent) in ("DocumentControl", "WindowControl"):
                    break
                contents = list(semantics.subtree(parent, limit=201, depth=12))
                if len(contents) >= 201:
                    break
                result = semantics.info_panel_kind(contents, contact)
                if result != "unknown":
                    return result
        return None

    result = _wait_value(panel)
    if result is None:
        win = _pywinauto_root(win, player)
        result = _wait_value(panel, timeout=2)
    _diagnose(player, win, "VERIFY_NOT_GROUP", backend="UIA/raw/MSAA contact-info", header=header)
    # Escape closes the info panel; it is never used as evidence that it closed.
    _sendinput_chord(hwnd, 0x1b)
    if result != "direct":
        raise _VerificationError("VERIFY_NOT_GROUP", "group conversation rejected" if result == "group" else "direct Contact info panel and exact name were not exposed")
    if not _wait_value(lambda: not any(semantics.norm(_control_name(c)) in ("contact info", "group info") and _control_type(c) == "TextControl" and _is_visible_enabled(c) for c in _walk(win))):
        raise _VerificationError("VERIFY_NOT_GROUP", "contact info panel did not close")
    header = _wait_value(lambda: _find_chat_header(win, contact))
    if header is None:
        raise _VerificationError("VERIFY_CHAT_HEADER", "chat changed after direct-contact verification")
    _log(player, f"VERIFY_NOT_GROUP verified backend=UIA/raw/MSAA Contact info name={contact!r}")
    return win, header


def _run_verified_call(
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
        return "WhatsApp Desktop is running, but its main window could not be detected. " + _process_diagnostic()

    hwnd = int(getattr(win, "NativeWindowHandle", 0) or 0)
    _diagnose(player, win, "DETECT_WHATSAPP")
    if not _force_foreground_hwnd(hwnd):
        return "FOCUS_WHATSAPP failed: WhatsApp is not the foreground window."
    _diagnose(player, win, "FOCUS_WHATSAPP")
    if _verify_call_started("", timeout=0.2):
        return "WhatsApp already has an active call UI; no second call was placed."

    win, search, backend = _open_verified_search(win, hwnd, player)
    _diagnose(player, win, "VERIFY_SEARCH_MODE verified", backend=backend, search=search)
    _enter_verified_contact(win, hwnd, search, contact, player, backend)

    result = _wait_value(lambda: _find_contact_result(win, contact))
    if result is None:
        win = _pywinauto_root(win, player)
        result = _wait_value(lambda: _find_contact_result(win, contact), timeout=2)
    _diagnose(player, win, "FIND_EXACT_DIRECT_CHAT_RESULT", backend="UIA/raw/MSAA", result=result)
    if result is None:
        return f"FIND_EXACT_DIRECT_CHAT_RESULT failed: no unique exact conversation title for '{contact}'. Member and message matches are excluded."
    if not _activate_verified_element(hwnd, result, player):
        return f"OPEN_RESULT failed: could not activate exact row for '{contact}'."
    header = _wait_value(lambda: _find_chat_header(win, contact))
    if header is None:
        win = _pywinauto_root(win, player)
        header = _wait_value(lambda: _find_chat_header(win, contact), timeout=2)
    _diagnose(player, win, "VERIFY_CHAT_HEADER", backend="UIA/raw/MSAA", header=header)
    if header is None:
        return f"VERIFY_CHAT_HEADER failed: no structural conversation header exactly '{contact}'; no call placed."
    win, header = _verify_direct_chat(win, hwnd, header, contact, player)
    _log(player, f"OPEN_RESULT verified backend=UIA/raw/MSAA direct chat={contact!r}")

    button = _wait_value(lambda: _find_call_button(win, intent, header=header))
    _diagnose(player, win, "FIND_VOICE_CALL_BUTTON", backend="UIA/raw/MSAA", button=button)
    kind = "video" if intent == "video_call" else "voice"
    if not button:
        return f"FIND_VOICE_CALL_BUTTON failed: no accessible {kind} call control. Visible buttons: {_visible_button_names(win)}"

    if _verify_call_started("", timeout=0.2):
        return "CLICK_VOICE_CALL stopped: an active call UI was already present."
    if not _activate_verified_element(hwnd, button, player):
        return f"CLICK_VOICE_CALL failed: could not activate the {kind} call control."

    if _verify_call_started(contact, timeout=10):
        _diagnose(player, win, "VERIFY_CALL_UI", header=header, button=button)
        return f"WhatsApp {kind} call started with {contact}."

    return f"VERIFY_CALL_UI failed: clicked {kind} call for {contact}, but no active call UI was verified."


def whatsapp_desktop_call(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Serialize calls from the desktop tool and the voice bridge."""
    if not _CALL_LOCK.acquire(blocking=False):
        return "A WhatsApp call request is already in progress."
    try:
        # JARVIS dispatches plugins on worker threads. Initialize COM on that
        # thread rather than relying on the import thread's COM apartment.
        initializer = getattr(auto, "UIAutomationInitializerInThread", nullcontext)
        with initializer(), _physical_pixel_context():
            return _run_verified_call(parameters, response, player, session_memory)
    except _VerificationError as exc:
        _log(player, str(exc))
        return str(exc)
    except Exception as exc:
        message = f"WhatsApp automation failed without verified success: {type(exc).__name__}: {exc}"
        _log(player, message)
        return message
    finally:
        _CALL_LOCK.release()
