import sys
import types
import unittest
from unittest.mock import patch

for name in ("psutil", "uiautomation", "numpy", "sounddevice"):
    sys.modules.setdefault(name, types.ModuleType(name))
from plugins import whatsapp_voice_bridge as bridge_module
from plugins.whatsapp_voice_bridge import CallState, WhatsAppVoiceBridge


class VoiceBridgeCallGateTests(unittest.TestCase):
    def setUp(self):
        self.bridge = WhatsAppVoiceBridge()
        self.bridge._detect_virtual_audio_cable = lambda: (None, None, None)

    def test_unverified_call_never_starts_audio(self):
        with patch.object(bridge_module, "_modern_whatsapp_call", return_value="VERIFY_CHAT_HEADER failed"):
            with patch("threading.Thread") as thread:
                result = self.bridge.start_call_and_bridge("Ganesh")
        self.assertIn("VERIFY_CHAT_HEADER failed", result)
        self.assertEqual(self.bridge.state, CallState.ERROR)
        thread.assert_not_called()

    def test_verified_call_starts_bridge(self):
        with patch.object(bridge_module, "_modern_whatsapp_call", return_value="WhatsApp voice call started with Ganesh."):
            with patch("threading.Thread") as thread:
                self.bridge.start_call_and_bridge("Ganesh")
        self.assertEqual(self.bridge.state, CallState.CONNECTING)
        self.assertEqual(thread.call_count, 2)


if __name__ == "__main__":
    unittest.main()
