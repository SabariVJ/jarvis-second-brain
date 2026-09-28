"""Read-only WhatsApp accessibility probe. Run from the interactive desktop."""
import argparse
import contextlib
import datetime
from pathlib import Path
import sys
from actions.whatsapp_desktop_call import _find_whatsapp_window, _diagnose, _whatsapp_pids
from actions.whatsapp_desktop_call import whatsapp_desktop_call, _walk, _control_name, _launch_whatsapp, _force_foreground_hwnd


def probe(focus=False):
    if focus:
        print("Restore WhatsApp:", _launch_whatsapp())
    print("WhatsApp PIDs:", sorted(_whatsapp_pids()))
    win = _find_whatsapp_window(2)
    if win is None:
        print("No WhatsApp UIA window is visible in this Windows session.")
        return 1
    if focus:
        print("Foreground:", _force_foreground_hwnd(int(win.NativeWindowHandle)))
    _diagnose(None, win, "PROBE_UIA")
    for ctl in _walk(win):
        try:
            print("UIA/raw", ctl.ControlTypeName, repr(_control_name(ctl)),
                  "role=", ctl.AriaRole, "id=", ctl.AutomationId,
                  "rect=", ctl.BoundingRectangle)
        except Exception as exc:
            print("UIA/raw stale element:", exc)
    hwnd = int(getattr(win, "NativeWindowHandle", 0) or 0)
    try:
        from pywinauto import Application
        app = Application(backend="uia").connect(handle=hwnd)
        wrapper = app.window(handle=hwnd)
        print("pywinauto UIA children:", len(wrapper.descendants()))
        for ctl in wrapper.descendants()[:100]:
            print(ctl.element_info.control_type, repr(ctl.element_info.name))
    except Exception as exc:
        print("pywinauto UIA probe failed:", exc)
    try:
        from pywinauto import Application
        app = Application(backend="win32").connect(handle=hwnd)
        wrapper = app.window(handle=hwnd)
        print("pywinauto Win32 children:", len(wrapper.descendants()))
        import uiautomation as auto
        for child in wrapper.descendants()[:30]:
            print("Win32 child:", child.handle, child.class_name(), repr(child.window_text()))
            root = auto.ControlFromHandle(child.handle)
            controls = list(_walk(root))
            print("Direct child HWND UIA count:", len(controls))
            for ctl in controls:
                parent = ctl.GetParentControl()
                print("Win32->UIA:", ctl.ControlTypeName, repr(_control_name(ctl)),
                      "role=", ctl.AriaRole, "id=", ctl.AutomationId,
                      "parent=", parent.ControlTypeName if parent else "", repr(_control_name(parent)),
                      "rect=", ctl.BoundingRectangle)
    except Exception as exc:
        print("pywinauto Win32 probe failed:", exc)
    return 0


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def main():
    parser = argparse.ArgumentParser(description="WhatsApp diagnostics and isolated verified call test")
    parser.add_argument("--call", metavar="NAME", help="place one verified voice call to this exact direct chat")
    parser.add_argument("--focus", action="store_true", help="restore WhatsApp before the read-only tree probe")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent / "logs"
    folder.mkdir(exist_ok=True)
    path = folder / ("whatsapp-call-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".log")
    print("Diagnostic log:", path)
    with path.open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(_Tee(sys.stdout, log)), contextlib.redirect_stderr(_Tee(sys.stderr, log)):
            if args.call:
                result = whatsapp_desktop_call({"contact_name": args.call, "intent": "voice_call"})
                print(result)
                return 0 if result == f"WhatsApp voice call started with {args.call}." else 2
            return probe(focus=args.focus)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    raise SystemExit(main())
