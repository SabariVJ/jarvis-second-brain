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

## Personal long-term memory (Phase 19)

Intentional personal memories live in the existing SQLite database and use a
source record for provenance. Local users can explicitly save, inspect, edit,
search and forget memories. A small conservative rule set may capture clear
first-person preferences, profile facts, project statements, decisions,
workflows, tasks and personal context; greetings, questions, research and
external provider content are not automatically persisted. Telegram can only
create a memory through an explicit remember command from an allowlisted user.
Credential-like values are rejected. Expiration, importance, confidence,
last-used time and update provenance are stored. The local Personal Memory
panel uses text-only rendering and never treats a memory as system instruction.

## Telegram Remote Jarvis (Phase 20)

Telegram long polling is disabled by default and starts only from a local UI
action after local environment configuration. The adapter validates private
chat type and sender ID allowlisting before reading a message body or requesting
a voice file. Voice files are bounded, kept in memory, passed to the configured
transcription provider, and discarded. Telegram chat reuses the Jarvis
orchestrator while suppressing automatic personal-memory capture; explicit
remember commands retain Telegram provenance. No arbitrary filesystem path is
accepted. Sharing uses only registered generated PDFs with a separate local
approval and an exact in-chat confirmation. Bot tokens never enter status data.

## Local invoice and document generation (Phase 21)

ReportLab renders invoices, reports, summaries and letters into the private
Jarvis data directory. A structured SQLite registry stores the type, title,
unique filename, hash, source note IDs, invoice details, sharing approval and
card state. The UI preview route resolves registry IDs, enforces path
containment and verifies the PDF hash before returning bytes. Invoice creation
collects required seller/customer/line-item fields, validates decimal totals
and only applies tax when explicitly supplied. Generation saves locally; it
does not send or email documents. Telegram can only read artifacts approved by
the local card.

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
| POST | /api/jarvis/context | Record a bounded, session-local H.O.L.O selection/open/graph event; note metadata is resolved server-side |
| POST | /api/jarvis/chat | Text or recognized transcript |
| GET | /api/tools | Typed allowlist, argument schemas, availability and permission class |
| POST | /api/tools/execute | Execute a registered tool; non-read actions are denied until an approval is attached |
| POST | /api/jarvis/voice-state | Validated client voice lifecycle |
| POST | /api/vision/screen | Single transient JPEG analysis, bounded and not persisted |
| POST | /api/vision/camera | Single transient camera frame analysis |
| GET | /api/focus | Local Focus Lock state |
| POST | /api/focus/{start,pause,resume,stop} | Explicit local session controls |
| GET | /api/integrations/gmail | Local OAuth configuration status, no token values |
| POST | /api/gmail/{list,thread,summarize,draft,reply-draft,send} | On-demand Gmail operations; send requires a separate exact confirmation |
| GET | /api/integrations/calendar | Local OAuth configuration status, no token values |
| POST | /api/calendar/{today,tomorrow,events,search,availability,create,reschedule,cancel} | On-demand Calendar queries and writes with explicit confirmation |
| POST | /api/briefing/morning | Explicitly requested briefing assembled from connected integrations and local brain state |
| GET | /api/memory/status | Counts and extraction errors |
| POST | /api/memory/reindex | Scan configured root only |
| POST | /api/memory/embed | Build explicitly enabled cloud vectors |
| GET | /api/memory/search?q=… | Hybrid/local search with citations |
| GET | /api/memory/document?id=… | Active indexed source snapshot |
| GET | /api/graph?focus=… | Bounded source-supported graph |

## Phase 22: Deep H.O.L.O context

Each tab session keeps one current context reference plus a 32-event ring buffer.
The current reference expires after 30 minutes and disappears when the server
restarts. Events cover note selection/open/move/crush, graph node selection and
expand/collapse, graph focus, and selection/open of supported research, memory,
email, Calendar, generated document/invoice, Focus and Telegram cards. Indexed
note and graph labels/path references come from the local database; client text
cannot replace them. Other card metadata is limited to short labels and kind.
No note body, email body, screenshot, conversation or arbitrary metadata is
stored in this context object, and this interaction stream is never copied into
long-term memory. It is descriptive context only: it cannot grant permission
or approve a tool action. “Summarize this” continues to use a verified selected
note through the existing retrieval path.

## Phase 23: Agent / tool registry

`jarvis.tools.Registry` is the typed execution boundary. Every definition has a
name, description, argument schema, permission class, availability, execution
function and optional result verifier. Validation rejects unknown fields, bad
types, out-of-range values and oversized nested objects. Results carry an
`ok` flag, structured error when applicable, and a verification state. Local
reads may execute; writes and external actions require a trusted server-side
authorizer. The HTTP route never accepts an approval flag from its caller.
Explicit personal-memory commands are recognized and routed through the same
registry. Windows actions, direct Telegram sending and screen capture are
registered as unavailable until their permission and user-gesture foundations
are ready. No shell or arbitrary PowerShell tool is registered, and Astra does
not receive unrestricted runtime function calling.

## Phase 24: Permission and approval engine

The local SQLite approval ledger binds each pending action to a validated tool,
canonical arguments and SHA-256 digest. Approvals expire after five minutes by
default (bounded from 30 seconds to 30 minutes), and confirmation must match
`APPROVE <approval-id>` exactly. Execution revalidates the grant against the
ledger and exact tool arguments; caller-supplied approval flags have no effect.
The visible local approval card redacts message bodies and secret-like fields.
Gmail send and Calendar create/reschedule/cancel flow through this ledger;
provider adapters still verify their action-specific confirmation and report
the provider's result before Jarvis claims success. Web, email, document,
screen, and Telegram content are arguments/data only and cannot approve.

## Phase 25: Persistent visual cards

`VisualCards` persists only when the user invokes Save. Payload fields are
allowlisted by card type, JSON is bounded, and credential-like nested keys are
rejected. Research content remains transient in its existing session store
unless the user explicitly saves a H.O.L.O card. Persistent cards can be opened,
expanded, pinned, dismissed or removed; dismissed cards remain recoverable until
removed. Their content is rendered as text. Only suitable summaries and
references are accepted for email, Calendar and approval cards.

## Phase 26: Integrations and settings

`GET /api/settings/status` exposes a fixed, secret-free status summary for
Astra, SQLite/indexing, browser voice and wake, screen vision, optional camera,
Focus Lock, Gmail, Calendar, Telegram, Windows tools and automations. It runs a
SQLite quick check and reports active indexed-source count. Browser microphone
and camera availability are checked only after a user gesture; server startup
never probes hardware. Provider configuration is represented by state and
setup guidance, never credential values. Unsupported features are labeled as
requiring setup or disabled rather than presented as connected.

## Phase 27: Safe Windows computer control

The Windows adapter exposes only fixed application aliases, public HTTP(S)
URLs, files/folders beneath the indexed notes and generated-document roots,
read-only active process/window inspection, and master playback volume. Launches
use a resolved executable with `shell=False`; local paths are canonicalized,
bounded to configured roots and reject script/executable file types. URLs reject
non-web schemes, embedded credentials and local hostnames. Mutating operations
use the Phase 24 approval ledger. Foreground title/process data are returned only
on direct query and never written to logs or memory. Screen capture stays with
the existing explicit browser display chooser; no screenshot is persisted. No
shell or arbitrary command execution is exposed. Volume and native foreground
inspection still need physical Windows acceptance.

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

## Phase 17: Google Calendar

The Calendar adapter reuses the local Google refresh-token client. Reads are
bounded by the requested date range and page limit. Free/busy uses the primary
calendar. Create, reschedule and cancel require both a browser confirmation and
an exact action phrase checked at the adapter boundary. Creation and rescheduling
are treated as complete only when Google's response contains the expected event
ID; cancellation is reported only after the delete request succeeds. Calendar
items remain in Google and are not persisted into the second brain. See
`SETUP.md` for the narrow OAuth scopes and local configuration.

## Phase 18: Morning briefing

`POST /api/briefing/morning` combines today's Calendar events, important/starred
Gmail metadata, source-backed priorities, active tasks, deadline/reminder memories,
recent projects and the current Focus target. Disconnected providers are labeled
and do not block local data. Email subjects and event titles are rendered as text;
email snippets are not spoken or passed to an AI. A concise spoken summary is
returned with the detailed structured card data. UI startup never calls this route
or starts speech; a user must press the briefing button or ask for it, and read-aloud
still follows the existing opt-in speech setting. Scheduling metadata explicitly
reports that automatic scheduling is unsupported and off, leaving a future hook
without starting a background job.
