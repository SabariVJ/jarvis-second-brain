import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("psutil", types.ModuleType("psutil"))
sys.modules.setdefault("uiautomation", types.ModuleType("uiautomation"))
from actions import whatsapp_desktop_call as wa


class Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class Control:
    def __init__(self, name, kind, rect):
        self.Name, self.ControlTypeName, self.BoundingRectangle = name, kind, rect
        self.IsEnabled, self.IsOffscreen = True, False


class VerifiedCallTests(unittest.TestCase):
    def setUp(self):
        self.window = Control("WhatsApp", "WindowControl", Rect(0, 0, 1600, 850))

    def test_result_must_be_exact_and_in_chat_list(self):
        bad = Control("Ganesh Kumar", "ListItemControl", Rect(50, 200, 350, 240))
        header = Control("Ganesh", "TextControl", Rect(600, 50, 700, 80))
        with patch.object(wa, "_walk", return_value=iter([bad, header])):
            self.assertIsNone(wa._find_contact_result(self.window, "Ganesh"))

    def test_header_must_be_exact_and_in_header_region(self):
        list_item = Control("Ganesh", "TextControl", Rect(50, 200, 350, 240))
        with patch.object(wa, "_walk", return_value=iter([list_item])):
            self.assertIsNone(wa._find_chat_header(self.window, "Ganesh"))

    def test_call_button_rejects_generic_history_item(self):
        history = Control("Call history", "ButtonControl", Rect(100, 100, 200, 130))
        with patch.object(wa, "_walk", return_value=iter([history])):
            self.assertIsNone(wa._find_call_button(self.window, "voice_call"))


if __name__ == "__main__":
    unittest.main()
