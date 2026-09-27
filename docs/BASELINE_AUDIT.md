# Baseline audit — 2026-09-27

Archive: `D:\Jarvis-halo\holo-gestures-main.rar`. Extracted into this repository;
original archive remains unchanged. Untouched baseline commit:
`278fe99f44907a4af3db2e9d3aacfb144970625d`. Branch: `jarvis-second-brain`.

## Architecture and inventory

26 supplied files: stdlib `server.py`, single-module `holo.html`, `holo.json`,
README/license, banner, eight sample Markdown notes, two CC0 GLB props, and local
Three.js/GLTFLoader/geometry/MediaPipe/model/WASM dependencies. No package manifest,
test runner, database or Git history supplied. Application source, all sample
notes and library entry points/shims inspected. Binary assets inventoried and
exercised in browser; generated vendor internals are not application code.

The threaded HTTP server binds 127.0.0.1:4890. Notes folder comes from holo.json,
falling back to sample-notes. Tree groups one directory level into folder orbs.
Note bodies are truncated to 420/4000 characters for cards/readers. State and
diagnostics are written under ignored state/. Page is cached as disk fallback.

GET: /, /holo.html, /api/notes, /api/tree, /api/props, /vendor/*, /props/*.
POST: /api/state, /api/diag. **GET /api/state returns 404 in the baseline.**

DOM cards and folder orbs use a physics loop; Three.js renders props on a separate
canvas. MediaPipe landmarks pass confidence/size/deduplication gates, stable hand
assignment and One Euro smoothing, then pinch/drag/release/two-hand logic.
Mouse uses the same card data. Effects are opt-in. Built-in speech is browser TTS;
summary is sentence extraction, not AI. Events debounce into /api/state.

Simulation uses synthetic landmarks through the same engine. Probe exercises
26 gesture/render assertions and puts results in document.title. Some prop checks
can silently skip absent props, so verification also checks GL and loaded objects.

## Measured baseline

Bundled Python launched `server.py`; Edge headless, 1440x1000, software WebGL:
- /: loads, five initial entities, GL true, no page/frame errors; camera absent.
- /?sim=1: scripted hands running, GL true, no page/frame errors.
- /?probe=1: **26/26**, both props loaded, no page/frame errors.
- /api/tree: 200, three folders/eight notes.
- /api/state: POST works; GET missing, as above.

Python 3.11 is installed under LocalAppData/Python, but `py` is not on this
execution environment's PATH. Preserve Python-compatible server.py; ship a
portable Windows launcher rather than silently changing the user's PATH.

## Extension points and risks

Add runtime/API modules around existing handler, stable source IDs on notes,
selection events at reader/grab/summary, separate graph/UI module. Preserve probe.
Risks: permissive POST parsing, unlimited request bodies, absent Origin/Host
validation, static path containment, concurrent state tempfile writes, stale note
identity by title, camera initialization even in probe, shortcut collisions with
text fields, unbounded personal-data exposure if new directories are served.
Personal DB/secrets must remain outside all static routes and Git.

Reference video URL could not be retrieved by the web tool. The supplied written
acceptance criteria define this build; no claim of having watched the video.
