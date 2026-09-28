import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("psutil", types.ModuleType("psutil"))
sys.modules.setdefault("uiautomation", types.ModuleType("uiautomation"))
from plugins import whatsapp_desktop_call as plugin


class CallRoutingTests(unittest.TestCase):
    def test_voice_call_uses_authoritative_action(self):
        with patch.object(plugin, "whatsapp_desktop_call", return_value="verified") as action:
            self.assertEqual(plugin.run({"intent": "voice_call", "contact_name": "Ganesh"}), "verified")
            action.assert_called_once()

    def test_unsupported_intent_does_not_start_call(self):
        with patch.object(plugin, "whatsapp_desktop_call") as action:
            self.assertIn("Unsupported", plugin.run({"intent": "end_call"}))
            action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
