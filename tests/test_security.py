import unittest

from jarvis.security import redact, contains_secret


class SecurityTests(unittest.TestCase):
    def test_shared_secret_detector_covers_assignments_and_provider_tokens(self):
        self.assertTrue(contains_secret('refresh token: local-value'))
        self.assertTrue(contains_secret('123456789:AAETelegramBotSecretToken12345'))
        self.assertTrue(contains_secret('Bearer access-token-value'))
        self.assertTrue(contains_secret('AIza123456789012345678901234567890'))
        self.assertFalse(contains_secret('A reminder about tomorrow morning.'))

    def test_secret_formats_are_redacted_from_errors_and_saved_text(self):
        value='sk-proj-supersecretkey123456 Bearer access-token-value ya29.a0AfH6SMBVeryLongGoogleToken123456 123456789:AAETelegramBotSecretToken12345 AIza123456789012345678901234567890 ghp_abcdefghijklmnopqrstuvwxyz123456'
        filtered=redact(value)
        self.assertEqual(filtered.count('[REDACTED]'),6)
        for secret in ('supersecretkey123456','access-token-value','VeryLongGoogleToken123456','AAETelegramBotSecretToken12345',
            'AIza123456789012345678901234567890','abcdefghijklmnopqrstuvwxyz123456'):
            self.assertNotIn(secret,filtered)
        self.assertEqual(redact('The key of the story is clarity.'),'The key of the story is clarity.')

    def test_credential_assignments_are_redacted_before_external_provider_requests(self):
        filtered=redact('Password: synthetic-value GEMINI_API_KEY=another-synthetic-value')
        self.assertNotIn('synthetic-value',filtered)
        self.assertEqual(filtered.count('[REDACTED]'),2)


if __name__=='__main__':unittest.main()
