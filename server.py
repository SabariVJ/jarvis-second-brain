#!/usr/bin/env python3
"""HOLO — hand-gesture control deck (Jarvis V7 prototype). Stdlib only, port 4890.

Serves the deck page + the note cards it manipulates. Hand tracking is Google
MediaPipe (Apache-2.0) loaded from CDN in the page; every gesture on top is ours,
written clean — no third-party gesture code. Camera frames never leave the page.

Endpoints:
  GET  /               → holo.html
  GET  /api/notes      → [{name, title, body}] from the folder in holo.json
                         (falls back to ./sample-notes so it runs instantly)
  POST /api/state      → future Jarvis hook: writes state/holo-state.json so the
                         big brain can react to what the hands did ("Card pinned,
                         sir"). Nothing reads it yet by design — prototype stays
                         standalone until proven.
"""
import json, os, time, threading
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from jarvis.core.runtime import Runtime
from jarvis.security import local_request
from jarvis.memory.database import stable_id

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("HOLO_PORT", "4890"))
RUNTIME = None
STATE_LOCK = threading.Lock()

# the page, cached at boot: long-lived processes on macOS can silently lose file
# access (TCC) hours in — serving the boot-time copy beats a 500 "missing" page
try:
    PAGE_CACHE = [Path(ROOT, 'holo.html').read_bytes()]
except OSError:
    PAGE_CACHE = [None]

def notes_dir():
    try:
        cfg = json.loads(Path(ROOT, 'holo.json').read_text(encoding='utf-8-sig'))
        d = os.path.expanduser(cfg.get("folder", ""))
        if d and not os.path.isabs(d): d = os.path.join(ROOT,d)
        if d and os.path.isdir(d):
            return d
    except Exception:
        pass
    return os.path.join(ROOT, "sample-notes")

def _note(path, n):
    try:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(Path(notes_dir()).resolve()): return None
        with resolved.open(encoding='utf-8', errors='ignore') as handle:
            text = handle.read(16000)
    except OSError:
        return None
    lines = [l for l in text.splitlines() if l.strip()]
    title = (lines[0].lstrip("# ").strip() if lines else n)[:48] or n
    rest = [l for l in lines[1:] if not l.startswith("#")]
    return {"name": n, "title": title, "body": "\n".join(rest)[:420],
            "full": "\n".join(lines[1:])[:4000],
            "document_id": stable_id('doc', str(Path(path).resolve()))}

def load_notes(limit=18):
    out = []
    d = notes_dir()
    try:
        for n in sorted(x for x in os.listdir(d) if x.endswith((".md", ".txt")))[:limit]:
            note = _note(os.path.join(d, n), n)
            if note: out.append(note)
    except OSError:
        pass
    return out

def load_tree(limit_files=14):
    """One level deep: subfolders become ORBS; loose root files gather under 'NOTES'."""
    d = notes_dir()
    tree = []
    try:
        entries = sorted(os.listdir(d))
        loose = []
        for e in entries:
            p = os.path.join(d, e)
            if os.path.isdir(p) and not e.startswith("."):
                files = []
                for n in sorted(x for x in os.listdir(p) if x.endswith((".md", ".txt")))[:limit_files]:
                    note = _note(os.path.join(p, n), n)
                    if note: files.append(note)
                if files:
                    tree.append({"kind": "folder", "name": e.upper()[:22], "files": files})
            elif e.endswith((".md", ".txt")):
                note = _note(p, e)
                if note: loose.append(note)
        if loose:
            tree.append({"kind": "folder", "name": "NOTES", "files": loose[:limit_files]})
    except OSError:
        pass
    return tree

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "frame-ancestors 'none'")
        self.send_header('Referrer-Policy', 'no-referrer')
        if ctype.startswith("text/html"):
            self.send_header("Cache-Control", "no-store")   # a stale cached page hid real fixes once
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    MIME = {".mjs": "text/javascript", ".js": "text/javascript",
            ".css": "text/css; charset=utf-8",
            ".wasm": "application/wasm", ".task": "application/octet-stream",
            ".glb": "model/gltf-binary"}

    def do_GET(self):
        if not local_request(self.headers, self.server.server_port):
            return self._send(403, {"error": "Local same-origin access only"})
        parsed = urlsplit(self.path)
        if parsed.path == '/api/documents/file' and RUNTIME:
            try:
                artifact=RUNTIME.documents.read_file(parse_qs(parsed.query).get('id',[''])[0])
                download=parse_qs(parsed.query).get('download',[''])[0]=='1'
                disposition='attachment' if download else 'inline'
                filename=artifact['filename']
                body=artifact['content']
                self.send_response(200)
                self.send_header('Content-Type','application/pdf')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"frame-ancestors 'self'")
                self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Disposition',f'{disposition}; filename="{filename}"')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body);return
            except ValueError as error:return self._send(404,{'error':str(error)})
            except Exception:return self._send(500,{'error':'Generated document could not be opened'})
        if RUNTIME:
            try:
                result = RUNTIME.dispatch('GET', parsed.path, {}, parse_qs(parsed.query))
                if result is not None: return self._send(200, result)
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            except Exception:
                return self._send(500, {'error': 'Operation failed; local data preserved'})
        if parsed.path == '/api/state':
            with STATE_LOCK:
                try:
                    with open(os.path.join(ROOT, 'state', 'holo-state.json')) as f:
                        return self._send(200, json.load(f))
                except (OSError, ValueError): return self._send(200, {})
        p = self.path.split("?")[0]
        if p in ("/", "/holo.html"):
            try:
                body = Path(ROOT, 'holo.html').read_bytes()
                PAGE_CACHE[0] = body
            except OSError:
                body = PAGE_CACHE[0]          # disk access lost (TCC) — serve the boot copy
            if body is None:
                return self._send(500, {"error": "holo.html missing"})
            return self._send(200, body, "text/html; charset=utf-8")
        if p == "/api/props":
            # PROPS: any .glb dropped into props/ becomes a grabbable 3D object
            try:
                names = sorted(x for x in os.listdir(os.path.join(ROOT, "props"))
                               if x.endswith(".glb"))[:6]
            except OSError:
                names = []
            return self._send(200, names)
        if p.startswith(("/vendor/", "/props/", "/ui/")):
            # self-hosted tracking libs: no CDN in the path, so ad-block extensions
            # and offline machines can't kill the hand tracking
            base = Path(ROOT, p.split('/')[1]).resolve()
            full = Path(ROOT, unquote(p).lstrip('/')).resolve()
            if full.is_relative_to(base):
                if os.path.isfile(full):
                    ext = os.path.splitext(full)[1]
                    try:
                        return self._send(200, full.read_bytes(),
                                          self.MIME.get(ext, "application/octet-stream"))
                    except OSError:
                        pass
            return self._send(404, {"error": "not found"})
        if p == "/api/notes":
            return self._send(200, load_notes())
        if p == "/api/tree":
            return self._send(200, load_tree())
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not local_request(self.headers, self.server.server_port, write=True):
            return self._send(403, {"error": "Local JSON requests only"})
        try:
            n = int(self.headers.get('Content-Length', '0'))
            limit = 800_000 if urlsplit(self.path).path in ('/api/vision/screen','/api/vision/camera') else 65536
            if n <= 0 or n > limit: return self._send(413, {'error': 'Invalid request size'})
            data = json.loads(self.rfile.read(n))
            if not isinstance(data, dict): raise ValueError('Object required')
        except (ValueError, UnicodeError):
            return self._send(400, {'error': 'Invalid JSON object'})
        parsed = urlsplit(self.path)
        if RUNTIME:
            try:
                result = RUNTIME.dispatch('POST', parsed.path, data, parse_qs(parsed.query))
                if result is not None: return self._send(200, result)
            except (ValueError, KeyError) as e:
                return self._send(400, {'error': str(e)})
            except Exception:
                return self._send(500, {'error': 'Operation failed; local data preserved'})
        p = self.path.split("?")[0]
        if p == "/api/diag":              # the page phones home its own crash report
            data["ts"] = time.time()
            try:
                os.makedirs(os.path.join(ROOT, "state"), exist_ok=True)
                with open(os.path.join(ROOT, "state", "holo-diag.json"), "w") as f:
                    json.dump(data, f, indent=2)
            except OSError:
                pass
            return self._send(200, {"ok": True})
        if p != "/api/state":
            return self._send(404, {"error": "not found"})
        data["ts"] = time.time()
        try:
            with STATE_LOCK:
                os.makedirs(os.path.join(ROOT, "state"), exist_ok=True)
                tmp = os.path.join(ROOT, "state", ".holo-state.tmp")
                with open(tmp, "w") as f:
                    json.dump(data, f)
                os.replace(tmp, os.path.join(ROOT, "state", "holo-state.json"))
        except OSError:
            return self._send(500, {'error': 'State could not be saved'})
        return self._send(200, {"ok": True})

class LocalServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can accidentally allow two servers on the same port.
    allow_reuse_address = False

    def server_bind(self):
        import socket
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

if __name__ == "__main__":
    RUNTIME = Runtime(ROOT, notes_dir)
    print(f"HOLO deck on http://localhost:{PORT}  ·  notes: {notes_dir()}")
    LocalServer(("127.0.0.1", PORT), H).serve_forever()
