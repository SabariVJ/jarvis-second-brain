"""Keep automated suites offline even when a developer has live keys configured."""
import os
import pytest


# Run at pytest import/session startup, before module-level app instances exist.
os.environ['AI_PROVIDER'] = 'offline'
os.environ.pop('GEMINI_API_KEY', None)
os.environ['OPENAI_API_KEY'] = ''


def pytest_sessionstart(session):
    os.environ['AI_PROVIDER'] = 'offline'
    os.environ.pop('GEMINI_API_KEY', None)
    os.environ['OPENAI_API_KEY'] = ''


@pytest.fixture(autouse=True)
def disable_live_gemini_for_tests(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'offline')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
