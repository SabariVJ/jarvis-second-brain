import base64
import json
import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from jarvis.ai.vision import Vision


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.image = b'\xff\xd8\xff' + b'x' * 100
        self.data_url = 'data:image/jpeg;base64,' + base64.b64encode(self.image).decode()
        self.client = Mock()
        self.client.responses.create.return_value = NS(status='completed', output_text=json.dumps({
            'answer':'The dialog says network unavailable.',
            'observations':['A warning dialog is centered.'], 'caution':'Visible text may be incomplete.'}))
        self.vision = Vision(client=self.client)

    def test_single_image_request_is_untrusted_and_not_stored(self):
        result = self.vision.analyze_screen('Why is this error happening?', self.data_url)
        self.assertIn('network unavailable', result['answer'])
        request = self.client.responses.create.call_args.kwargs
        self.assertFalse(request['store'])
        self.assertIn('untrusted', request['instructions'])
        self.assertEqual(request['input'][0]['content'][1]['image_url'], self.data_url)
        self.assertNotIn('tools', request)

    def test_invalid_and_oversize_images_are_rejected_before_api(self):
        for image in ('https://example.org/a.jpg', 'data:image/png;base64,AAAA',
                      'data:image/jpeg;base64,@@@@',
                      'data:image/jpeg;base64,' + base64.b64encode(b'nope').decode(),
                      'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xff'+b'x'*512001).decode()):
            with self.subTest(image=image[:36]), self.assertRaises(ValueError):
                self.vision.analyze_screen('Explain this screen', image)
        self.client.responses.create.assert_not_called()

    def test_invalid_question_and_unconfigured_service_fail_safely(self):
        with self.assertRaises(ValueError): self.vision.analyze_screen('', self.data_url)
        with patch.dict(os.environ, {'OPENAI_API_KEY':''}):
            with self.assertRaisesRegex(ValueError, 'No screenshot was saved'):
                Vision().analyze_screen('What is this?', self.data_url)

    def test_malformed_model_output_is_rejected(self):
        self.client.responses.create.return_value = NS(status='completed', output_text='{}')
        with self.assertRaises(ValueError): self.vision.analyze_screen('Explain this', self.data_url)


if __name__ == '__main__': unittest.main()
