# Jarvis foundation

`server.py` remains the entry point. H.O.L.O's single-module gesture engine,
local vendor files and props are retained. New functionality is composed around it.

```text
H.O.L.O card events ─┐
Text / transcript ──┼─> same-origin HTTP ─> per-tab context + state machine
Galaxy selection ───┘                         │
                                      read-only tool registry
                                             │
                      SQLite FTS / filenames / vectors / recency
                                             │
                        verified source IDs + source text (untrusted)
                                             │
                     Responses API or labelled local extract
                                             │
                      source buttons + graph focus + optional TTS
```

## Runtime and trust

The app binds only 127.0.0.1. Host and Origin checks reject DNS rebinding/cross-site
access; write requests require JSON and have a 64 KiB limit, except the bounded
single-frame screen/camera vision endpoints (800 KiB). No CORS headers are
emitted. Static serving is limited to vendor, props and ui with resolved path
containment. Notes cannot escape their configured root via symlinks. Data, .env,
Python source and Git are never statically served. This protects a local browser
application, not against another malicious process already running as the user.

Contexts are per-tab opaque sessions, capped at 64, expire after an hour; selection
expires after 30 minutes. At most one chat per session runs at once. History keeps
only six short-lived messages in RAM. No default persistent transcripts or automatic
fact extraction. State events contain state/time/sequence, not source contents.

All requests enter a validated state machine. Text starts at RETRIEVING; browser
voice reports LISTENING/TRANSCRIBING, then uses the same chat route. Browser
recognition shows interim text without submitting it; only a final result enters
chat. The microphone control can cancel listening, and failed starts reset it.
TTS reports SPEAKING and stop reports INTERRUPTED. An opt-in browser wake mode
listens for “Jarvis” and can accept a command in the same phrase or the next
phrase. During playback, a separate one-shot recognizer accepts only exact
interruption phrases; it filters phrases present in the text being spoken and
waits through a start/end cooldown. Wake recognition stays paused until playback
ends. Read-aloud mute and Stop speech both cancel the utterance. Browser speech
recognition is online in some browsers, and acoustic behavior still needs local
hardware acceptance. Camera is explicit through RETRY CAMERA or ?camera=1.
Simulation/probe never need hardware. Existing J mode remains the gesture narrator.

Screen analysis starts only from an explicit screen question or the one-shot
screen button. The browser display chooser selects a monitor, window or tab; one
scaled JPEG frame is captured, the display tracks are stopped, and only then is
the image sent for analysis. The screenshot is bounded, processed in memory and
never added to notes, chat history or logs. Screen text is untrusted image data;
vision returns a bounded structured answer and observations, with no tools or
ability to click controls. Live analysis needs the user's OpenAI configuration.
The optional Jarvis Eyes button uses the same one-frame vision adapter through a
separate explicit camera permission request. Its visible lifecycle is CAMERA
READY, ACTIVE, UNAVAILABLE or ERROR; it stops the camera tracks after one frame.
H.O.L.O camera startup and simulation remain independent.

The tool registry only exposes validated read operations. Risk >0 is denied
unconditionally, with no `approved=true` bypass. A proper single-use approval
ledger must precede future side-effect integrations. Source content is put in
the user-data payload, never interpolated into system instructions. The model
receives no executable tool authority. This is structural isolation; it does not
guarantee perfect model factual accuracy. Returned citation IDs must belong to
retrieved evidence, or the answer falls back to a labelled local extract.

## Memory and provenance

SQLite WAL with foreign keys, per-operation connections and transactions. Schema
version 1; future versions must use explicit migrations, never silently downgrade.

- Sources retain root, actual path, relative path, byte fingerprint, timestamps,
  media type and active/deleted/error status.
- Documents keep title/full extracted text and source ID. Chunks keep exact
  character offsets and ordinal; IDs change on source-content change.
- FTS5 indexes chunk text/title/path. Vectors are keyed by chunk ID and embedding
  model, preventing cross-model mixing.
- Entities are explicit headings, hashtags and wikilinks. MENTIONS edges carry
  source ID, exact supporting text and confidence. No invented HAS_SYSTEM/USES
  claims. Entity provenance is through its supported edges.
- Memory, conversation, task, project and person tables require source IDs;
  user-facing long-term-memory workflows remain Phase 19.

Indexing scans Markdown, UTF-8 text and text PDFs read-only. Extraction limits:
20 MiB input, 2 million characters, 500 PDF pages. Encrypted/scanned PDFs report
an actionable error; OCR is not implemented. Reader registry is the extension
point for DOCX, spreadsheets, code and images. Reindex is manual/startup, not a
filesystem watcher. Failed reads quarantine stale content from retrieval.
Unchanged byte fingerprints skip work. Missing files are tombstoned; historical
text remains local, but deleted/error sources are excluded from answers and graph.
A failed folder traversal never runs deletion reconciliation.

Distinct paths with identical bytes retain independent provenance. Search merges
identical-content results and records duplicate paths. Modified/deleted sources
cannot be used as active evidence after reindex. Switching configured roots
revokes visibility of old roots. A future forget operation must purge historical
data explicitly rather than merely tombstone it.

## Retrieval and AI

Hybrid ranking combines FTS rank, fuzzy filename/title match, opt-in semantic cosine
similarity, metadata and weak recency. No key means honest keyword/fuzzy mode;
hash vectors are not presented as semantics. OpenAI embeddings require explicit
JARVIS_EMBEDDINGS=openai and a button/API action to upload chunks. Query embedding
then happens during search. Changed sources need semantic reindexing too.

Default brain is `gpt-6-astra`, configured via JARVIS_MODEL. Official Python SDK
Responses API, structured JSON answer/citations, store=False, bounded output,
timeouts, at most one retry. Citation navigation is constructed only from database
IDs. Selected-note and named-note summaries read the full indexed body up to
80,000 characters with a visible partial-coverage notice above that limit.
Offline summaries are labelled sentence extracts, not simulated AI output.

Graph view is bounded to 300 nodes (up to 150 documents, remainder entities).
Search can load a focused graph outside the initial set. Clickable evidence shows
why a relation exists. Confidence controls edge opacity; retrieved sources are
larger/gold. Selection/focus APIs are ready for later graph-specific gestures.
Existing hand gestures still manipulate the original H.O.L.O objects.

Current retrieval scans active chunks/vectors in Python: adequate for foundation
collections, not a benchmarked massive vault. Before large-scale rollout, measure
10k–100k documents and add vector ANN/candidate filtering, paging and worker jobs.
Do not claim large-vault performance from the eight supplied sample notes.

## APIs

Original APIs are preserved; GET /api/state was added. New endpoints:

| Method | Route | Purpose |
|---|---|---|
| GET | /api/health | Configured/local state; no secret values |
| POST | /api/jarvis/session | Create tab session |
| GET | /api/jarvis/state?session_id=… | State and bounded event history |
| POST | /api/jarvis/context | Select/clear verified document ID |
| POST | /api/jarvis/chat | Text or recognized transcript |
| POST | /api/jarvis/voice-state | Validated client voice lifecycle |
| POST | /api/vision/screen | Single transient JPEG analysis, bounded and not persisted |
| POST | /api/vision/camera | Single transient camera frame analysis |
| GET | /api/focus | Local Focus Lock state |
| POST | /api/focus/{start,pause,resume,stop} | Explicit local session controls |
| GET | /api/integrations/gmail | Local OAuth configuration status, no token values |
| POST | /api/gmail/{list,thread,summarize,draft,reply-draft,send} | On-demand Gmail operations; send requires a separate exact confirmation |
| GET | /api/memory/status | Counts and extraction errors |
| POST | /api/memory/reindex | Scan configured root only |
| POST | /api/memory/embed | Build explicitly enabled cloud vectors |
| GET | /api/memory/search?q=… | Hybrid/local search with citations |
| GET | /api/memory/document?id=… | Active indexed source snapshot |
| GET | /api/graph?focus=… | Bounded source-supported graph |

## Phase 15: Focus Lock

Focus Lock starts only after the user presses Start or asks for a focus session.
On Windows a five-second background sampler reads the foreground process name
and window title through read-only window APIs. It does not capture keyboard
input, screenshots or page contents. The raw title exists only for in-memory
matching against the user's allow and distraction rules; it is never logged or
persisted. Local `data/focus.json` stores the goal, rules, start/end times,
duration, pauses, focus seconds, distraction count and outcome. Browser URL
inspection is not available in this local web app; browser tab titles can match
user-provided site keywords. On platforms without Windows window APIs the timer
and controls remain available while app monitoring reports unavailable.

## Phase 10: web research

An explicit “research …” or “search the web …” request calls the official Responses
`web_search` tool with required tool choice. The server accepts a result only when
the web-search call completed and the final answer contains usable URL citation
annotations. Cited URLs are validated for HTTPS public hostnames before display.
Source cards carry title, URL and an excerpt from the cited **answer**; that excerpt
is not represented as a quote from the webpage. If fewer than two sources were
cited, the UI warns that the result was not cross-checked. No fetched page can
change Jarvis tool permissions or reach the local static server.

Research cards live only in the tab's expiring session. Keep pins a temporary card;
Dismiss removes it. Save to brain is an explicit local write which creates an
indexed, source-backed research document with cited links and a prominent untrusted
web-derived label. The folder reindexer preserves this special root. Saving does
not silently trust the content. No autonomous card persistence occurs.

`GET /api/research/cards?session_id=…` lists a tab's cards; `POST
/api/research/card` accepts keep, dismiss or save for a card owned by that tab.
No API credentials means an explicit unavailable response and no card.

## Phase 16: Gmail

The Google OAuth client exchanges a locally configured refresh token for a
short-lived access token in memory. Secrets are read only from process environment
variables and never returned by status routes. Gmail access is on demand; messages
and summaries are not copied into the local brain or persisted. Email text is
untrusted input. Draft and reply-draft operations create provider-side drafts;
send additionally checks the exact `SEND <draft-id>` phrase server-side after a
browser confirmation. The default disconnected state is explicit. See
`SETUP.md` for local OAuth setup; automated integration coverage uses mocks.
