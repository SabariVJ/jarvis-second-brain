"""Local HTTP trust boundary; never infer permissions from model/source content."""
import re
from urllib.parse import urlsplit

def local_request(headers, port, write=False):
    allowed = {f'localhost:{port}', f'127.0.0.1:{port}'}
    if headers.get('Host', '').lower() not in allowed:
        return False
    if headers.get('Sec-Fetch-Site') == 'cross-site':
        return False
    origin = headers.get('Origin')
    if origin:
        u = urlsplit(origin)
        if u.scheme != 'http' or u.netloc.lower() not in allowed:
            return False
    if write and headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
        return False
    return True

def redact(text):
    value=str(text)
    patterns=(
        r'(?i)\b(?:sk-[a-z0-9_-]+|AIza[0-9A-Za-z_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,})\b',
        r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*',
        r'\bya29\.[A-Za-z0-9._-]{20,}',
        r'\b\d{6,}:[A-Za-z0-9_-]{20,}',
    )
    for pattern in patterns:value=re.sub(pattern,'[REDACTED]',value)
    return value
