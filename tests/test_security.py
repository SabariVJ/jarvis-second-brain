import unittest

from jarvis.security import redact


class SecurityTests(unittest.TestCase):
    def test_secret_formats_are_redacted_from_errors_and_saved_text(self):
        value='sk-proj-supersecretkey123456 Bearer access-token-value ya29.a0AfH6SMBVeryLongGoogleToken123456 123456789:AAETelegramBotSecretToken12345 AIza123456789012345678901234567890 ghp_abcdefghijklmnopqrstuvwxyz123456'
        filtered=redact(value)
        self.assertEqual(filtered.count('[REDACTED]'),6)
        for secret in ('supersecretkey123456','access-token-value','VeryLongGoogleToken123456','AAETelegramBotSecretToken12345',
            'AIza123456789012345678901234567890','abcdefghijklmnopqrstuvwxyz123456'):
            self.assertNotIn(secret,filtered)
        self.assertEqual(redact('The key of the story is clarity.'),'The key of the story is clarity.')


if __name__=='__main__':unittest.main()
