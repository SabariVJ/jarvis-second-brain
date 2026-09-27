# Run and verify

Open a terminal in this repository. Windows launcher:

```powershell
.\launch.cmd
```

Then open http://localhost:4890. Use SECOND BRAIN to toggle galaxy view. Camera
starts only when explicitly enabled. Search works with text without any hardware.
`/?sim=1` runs synthetic hands; `/?probe=1` runs the original 26 checks.

The normal Python entry point is unchanged:

```powershell
py server.py
```

**Host limitation:** this run could not resolve the system `py` command. The
installed Python 3.11 interpreter and project .venv successfully run server.py.
launch.cmd selects .venv first and works here. If your terminal also cannot find
py, use launch.cmd or enable/install the Windows Python launcher. We did not
change your global PATH or install a system launcher.

For a fresh clone, Python 3.11+ is sufficient for H.O.L.O and Markdown/text memory.
Install optional SDK/PDF dependencies in a local environment:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

37 Python tests cover states, isolation, security, ingestion, provenance, search,
mocked vectors, source selection, SDK wire contract and actual PDF parsing. Without
optional packages two integration tests skip; that is not a full acceptance pass.

Browser regression (Edge installed; local server running in another terminal):

```powershell
npm install
npm run test:browser
```

It asserts 26/26 and two loaded props (preventing silent prop skips), runs simulation,
no-camera startup, search/source/summary follow-ups, graph expand/collapse,
keyboard isolation, mocked voice and screen capture, interruption/echo cases,
reindex, narrow viewport and zero page errors. Screenshots go to ignored
test-results/. It never activates real microphone, screen share or camera. Browser tests expect the supplied sample-notes folder
and local/offline AI configuration; point tests at a separate local instance if
your production notes or credentials are configured.

## Notes folder

Edit holo.json locally with an absolute folder path or a repository-relative one:

```json
{"folder":"C:/MyNotes"}
```

Restart or select Reindex notes. No source file is modified. PDF extraction requires
pypdf; scanned PDFs need external OCR. Index and history are in ignored data/.
Changing holo.json does not make its path a secret; avoid committing personal paths.
Graph and source reader show indexed snapshots: reindex after external edits.

## OpenAI — user action required for live validation

No key was found and no live requests were made. Create/use an API key privately
in the OpenAI Platform; do not paste it into chat or source files. Set it in the
launching process or your preferred secure environment configuration. Example
PowerShell input that does not echo the secret:

```powershell
$secureKey = Read-Host 'OpenAI API key (local only)' -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
$env:JARVIS_MODEL = 'gpt-6-astra'
.\launch.cmd
```

The app reads environment variables; it does not automatically load .env files.
Setting the key enables sending the request, recent in-memory context and selected
retrieved note text to OpenAI for answers. `store=False` is requested; this is not
a promise about all provider retention. API usage may incur charges.

For semantic search, additionally set before launch:

```powershell
$env:JARVIS_EMBEDDINGS = 'openai'
$env:JARVIS_EMBEDDING_MODEL = 'text-embedding-3-small'
```

Then choose Build semantic index. This explicitly sends active note chunks to
OpenAI and saves vectors locally. Ordinary reindexing does not upload chunks.
Remove the embedding setting to return to keyword/fuzzy retrieval.

Live acceptance: index your authorized notes, search a paraphrase with little
lexical overlap, verify the correct path, select a note, summarize it, inspect
citations and test recovery after disconnecting internet. A configured key is not
the same as a verified account/model connection.

Phase 10 research also uses the same configured OpenAI key. Ask “Research current
alternatives to X” by text or optional browser voice. The hosted `web_search`
tool may incur additional charges. Cards cite clickable sources and remain
temporary; Keep pins one for this tab, while Save to brain explicitly indexes it
locally. With no key, research reports unavailable and local notes still work.
Live research quality and source coverage require an authorized account test.

Official references checked 2026-09-27:
- https://developers.openai.com/api/docs/models/gpt-6-astra
- https://developers.openai.com/api/docs/quickstart

## Voice and screen understanding

Use browser voice is push-to-talk or opt-in wake mode. Browser speech recognition
may use its vendor's online service. It has no dependency on the camera. While
Jarvis speaks, exact interruption phrases can stop playback; recognition pauses
for cooldown and suppresses phrases found in the answer being spoken. Actual
device availability and acoustic echo behavior require local microphone testing.

Screen analysis starts from an explicit screen question or the “Explain current
screen once” button. The browser chooser asks which monitor, window or tab to
share. Jarvis captures one scaled JPEG frame, stops the display tracks, and sends
the frame for analysis. It does not save the screenshot in notes or history.
This uses the configured OpenAI API key and can incur usage charges. On-screen
text is treated as untrusted data; Jarvis cannot click controls. Browser tests use
a generated fixture image and do not open the real screen chooser.
The image adapter follows the [Responses API image input guide](https://developers.openai.com/api/docs/guides/images-vision).

The optional “Look at this once” control requests camera access only after a
click or an explicit camera question. It captures one frame, stops camera tracks,
and discards the image after analysis. A camera is not required to launch Jarvis
or use H.O.L.O simulation; live image analysis uses the same API key as screen
understanding.

The H.O.L.O Focus Lock card tracks a local focus timer and, on Windows, samples
the foreground process and window title every five seconds only while a session
is active. Raw titles are matched in memory and discarded; local session totals
and your focus rules are saved in `data/focus.json`. It does not record keys or
screenshots. Browser URLs are not inspected; a tab title can match the site
keywords you enter. On other operating systems the focus timer and buttons work
without application monitoring.

Gmail, Calendar and Telegram are **not implemented** in this foundation. There is
no connection setup to perform yet; do not add tokens speculatively. Implement
their OAuth/allowlist/approval layers in phases 16, 17 and 20 first. No external
messages, events or other side-effect actions can be sent by the current runtime.
