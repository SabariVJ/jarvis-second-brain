import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("psutil", types.ModuleType("psutil"))
sys.modules.setdefault("uiautomation", types.ModuleType("uiautomation"))
from actions import whatsapp_desktop_call as wa


class CallStateTests(unittest.TestCase):
    def test_action_never_calls_without_contact(self):
        self.assertIn("exact saved", wa.whatsapp_desktop_call({"contact_name": ""}))

    def test_parallel_request_is_rejected(self):
        wa._CALL_LOCK.acquire()
        try:
            self.assertIn("already in progress", wa.whatsapp_desktop_call({"contact_name": "Ganesh"}))
        finally:
            wa._CALL_LOCK.release()

    def test_call_ui_requires_end_call_button(self):
        class Control:
            Name = "Calling Ganesh"
            ControlTypeName = "TextControl"
            IsEnabled = True
            IsOffscreen = False
        with patch.object(wa, "_whatsapp_windows", return_value=[object()]):
            with patch.object(wa, "_walk", return_value=iter([Control()])):
                self.assertFalse(wa._verify_call_started("Ganesh", timeout=0.01))


if __name__ == "__main__":
    unittest.main()
