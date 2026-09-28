"""Small, no-tool Gemini REST adapter for the existing Astra contract.

Requests use the official generateContent endpoint directly. This avoids
assuming the OpenAI Responses API schema is compatible with Gemini. Request
bodies and provider error bodies are never logged or included in exceptions.
"""
import json
import os
import re
from urllib.parse import quote
from urllib.request import Request, urlopen
from jarvis.security import contains_secret


API_ROOT = 'https://generativelanguage.googleapis.com/v1beta'
DEFAULT_GEMINI_MODEL = 'gemini-3.8-flash'
MODEL_RE = re.compile(r'^[A-Za-z0-9._-]{1,100}$')
MAX_RESPONSE_BYTES = 1_000_000


def valid_model_name(model):
    return (isinstance(model, str) and MODEL_RE.fullmatch(model) is not None
            and model.startswith('gemini-') and not contains_secret(model))


class GeminiUnavailable(ValueError):
    """Generic provider error that intentionally excludes remote details."""


def select_provider(environ=None):
    """Choose one provider; an explicitly selected provider never falls through."""
    environ = os.environ if environ is None else environ
    requested = str(environ.get('AI_PROVIDER', '')).strip().casefold()
    if requested:
        return requested if requested in {'gemini', 'openai', 'offline'} else 'offline'
    # Preserve the prior OpenAI-key-only setup for existing users. Gemini is
    # always explicit because its Free Tier has different data-use terms.
    return 'openai' if environ.get('OPENAI_API_KEY') else 'offline'


class GeminiAPI:
    """Bounded JSON REST transport for Gemini text, image, and inline audio."""

    def __init__(self, api_key, model=DEFAULT_GEMINI_MODEL, timeout=45, opener=None):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError('Gemini API key is not configured')
        if not valid_model_name(model):
            raise ValueError('Gemini model configuration is invalid')
        self._api_key = api_key.strip()
        self.model = model
        self.timeout = max(1, min(int(timeout), 60))
        self._opener = opener or urlopen

    def generate_text(self, parts, system_instruction='', response_schema=None,
                      max_output_tokens=1800):
        if not isinstance(parts, list) or not parts or len(parts) > 8:
            raise ValueError('Gemini content parts are invalid')
        if not isinstance(system_instruction, str) or len(system_instruction) > 12000:
            raise ValueError('Gemini system instruction is invalid')
        if not isinstance(max_output_tokens, int) or not 1 <= max_output_tokens <= 8192:
            raise ValueError('Gemini output limit is invalid')
        generation = {'maxOutputTokens': max_output_tokens}
        if response_schema is not None:
            if not isinstance(response_schema, dict):
                raise ValueError('Gemini response schema is invalid')
            generation.update({'responseMimeType': 'application/json',
                               'responseSchema': response_schema})
        payload = {
            'contents': [{'role': 'user', 'parts': parts}],
            'generationConfig': generation,
        }
        if system_instruction:
            payload['systemInstruction'] = {'parts': [{'text': system_instruction}]}

        request = Request(
            f'{API_ROOT}/models/{quote(self.model, safe="")}:generateContent',
            data=json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'x-goog-api-key': self._api_key,
                     'x-goog-api-client': 'jarvis-holo/1.0'},
            method='POST')
        try:
            with self._opener(request, timeout=self.timeout) as response:
                status = getattr(response, 'status', 200)
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except Exception:
            raise GeminiUnavailable('Gemini request failed; local fallback is available.') from None
        if status < 200 or status >= 300 or len(raw) > MAX_RESPONSE_BYTES:
            raise GeminiUnavailable('Gemini request failed; local fallback is available.')
        try:
            result = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GeminiUnavailable('Gemini returned an invalid response.') from None
        candidates = result.get('candidates') if isinstance(result, dict) else None
        if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
            raise GeminiUnavailable('Gemini returned no usable response.')
        candidate = candidates[0]
        finish = candidate.get('finishReason')
        if finish not in (None, 'STOP'):
            raise GeminiUnavailable('Gemini response did not complete.')
        content = candidate.get('content')
        response_parts = content.get('parts') if isinstance(content, dict) else None
        if not isinstance(response_parts, list):
            raise GeminiUnavailable('Gemini returned no usable response.')
        text_parts = [part['text'] for part in response_parts
                      if isinstance(part, dict) and isinstance(part.get('text'), str)
                      and not part.get('thought')]
        if not text_parts or not ''.join(text_parts).strip():
            raise GeminiUnavailable('Gemini returned no usable text.')
        return ''.join(text_parts)


def current_gemini_api(environ=None):
    environ = os.environ if environ is None else environ
    key = environ.get('GEMINI_API_KEY', '')
    model = environ.get('GEMINI_MODEL', DEFAULT_GEMINI_MODEL).strip()
    if not isinstance(key, str) or not key.strip() or not valid_model_name(model):
        return None
    return GeminiAPI(key, model)
