# JARVIS build progress — continuation through Phase 29, 2026-09-28

Branch: `jarvis-second-brain`.
Phase 22–31 run start SHA: `169d50e08a14823622d2a586035eb688054944ef`.
Recovered checkpoint before this continuation: `a73081a40c8cdffec16f732a635d729746b90a97`.
The original archive on D: is unchanged.

Phases 0–28 are preserved and complete. Live account and physical device
acceptance remain pending. This is not a full video-parity claim.

## Phase status, files, validation and remaining work

| Phase | Status | Main files | Validation | Commit | Remaining |
|---|---|---|---|---|---|
| 0 Audit | Complete, host launcher caveat | BASELINE_AUDIT.md | Probe 26/26, sim, root, tree, state POST | 278fe99, 63285c7 | Native py absent from tool PATH; launch.cmd verified |
| 1 Runtime | Complete | core/runtime.py, server.py | HTTP tests, actual restart | fc74313 | None |
| 2 State machine | Complete foundation | core/state.py, context.py, ui/jarvis.js | State paths, isolation, voice lifecycle | fc74313, ba9a487 | Spoken interruption remains in Phase 12 |
| 3 Second brain | Complete foundation | memory/database.py, graph.py | Provenance FKs, evidence, active-only graph | f2aa1f8 | Long-term memory workflows are complete in Phase 19 |
| 4 Ingestion | Complete supported formats | memory/ingestion.py | MD/TXT/PDF, fingerprints, idempotence, changes/deletes, offsets | f2aa1f8, ba9a487 | OCR and other formats deferred |
| 5 Semantic retrieval | Implemented, live pending | embeddings.py, retrieval.py | Mock semantic paraphrase, local FTS/fuzzy, model-keyed vectors | 03815ed | Authorized real vectors and personal-corpus relevance; offline is keyword/fuzzy |
| 6 Astra | Implemented, live pending | ai/astra.py, orchestrator.py, tools.py | Official SDK mocked HTTP, citations, failure fallback | 03815ed, ba9a487 | Account/model access with authorized credentials |
| 7 Galaxy | Complete foundation | ui/galaxy.js, jarvis.js/css, holo.html | Browser focus/select/source/expand/collapse, mouse/keyboard, sim | ba9a487 | Dedicated graph gestures later; original gestures retained |
| 8 Voice file search | Implemented, hardware pending | browser recognition, orchestrator | Mock transcript through actual HTTP search, follow-ups | ba9a487 | Real microphone/STT test |
| 9 Summaries | Implemented, live pending | astra.py, orchestrator, HOLO bridge | Selected/named-source tests, mock AI, local extracts | 03815ed, ba9a487 | Live summary quality |
| 10 Live research | Complete, live credential pending | research.py, orchestrator.py, runtime.py, ui/jarvis.js | 27 Python tests, mocked SDK HTTP, browser cards/offline flow, probe 26/26 | 45719c8 | Authorized live search quality |
| 11 Voice | Browser foundation complete, hardware pending | ui/jarvis.js | Interim/final recognition, cancel, lifecycle browser acceptance; probe 26/26 | 780f1cc | Real microphone/VAD acceptance |
| 12 Wake/interruption | Complete, hardware acceptance pending | ui/jarvis.js, runtime.py | Mock stop/cancel/enough, echo filter, TTS wake suppression/resume, mute, denied/unavailable speech; probe 26/26 | 1cdad6a | Real microphone/acoustic acceptance |
| 13 Screen vision | Complete, live key acceptance pending | ai/vision.py, runtime.py, server.py, ui/jarvis.js | 32 Python tests, prompt boundary/image validation, explicit picker/capture/discard, mocked endpoint; probe 26/26 | 77cfd8e | Live vision account acceptance |
| 14 Jarvis Eyes | Complete, hardware/key acceptance pending | ai/vision.py, runtime.py, ui/jarvis.js | Camera states, fake frame, track disposal, unavailable/denied paths; no-camera simulation green | e903720 | Physical camera acceptance |
| 15 Focus Lock | Complete, physical Windows monitoring acceptance pending | focus.py, runtime.py, ui/jarvis.js, H.O.L.O Focus card | 37 Python tests, mocked Win32 foreground read, title-free persisted history, controls/voice commands, browser acceptance | 5c52c3c | Verify live foreground classification on Windows |
| 16 Gmail | Complete code/mocks/UI, OAuth user setup required | integrations/google_oauth.py, gmail.py, runtime.py, ui/jarvis.js | 44 Python tests; mocked OAuth/API, disconnected state, inbox/unread/search/thread/local summary/draft/reply/send confirmation; browser acceptance and probe 26/26 | dbde059 | User must configure local Google OAuth before live Gmail use |
| 17 Calendar | Complete code/mocks/UI, OAuth user setup required | integrations/calendar.py, runtime.py, ui/jarvis.js | 51 Python tests; mocked today/tomorrow/range/search/free-busy and create/reschedule/cancel confirmation; browser acceptance and probe 26/26 | eda74d3 | User must configure Calendar OAuth scopes before live use |
| 18 Morning briefing | Complete code/mocks/UI, OAuth user setup required for live data | briefing.py, runtime.py, ui/jarvis.js, H.O.L.O briefing card | 55 Python tests; disconnected/failure fallbacks, source-backed brain inputs, mock integrations, manual-only card/voice; browser acceptance and probe 26/26 | 38d6d70 | Optional Google OAuth setup for live Gmail and Calendar inputs |
| 19 Long-term Memory | Complete | memory/long_term.py, database.py, orchestrator.py, runtime.py, ui/jarvis.js | 65 Python tests; probe 26/26; launch health; browser panel; full browser suite later passed | 1c71e9b | None |
| 20 Telegram Remote Jarvis | Complete, account setup required for live use | integrations/telegram.py, runtime.py, ui/jarvis.js | Allowlist, polling, voice mocks, approved-file two-step tests; browser disabled-state acceptance; probe 26/26 | 0c483dc | Configure a local bot token and allowlist for live verification |
| 21 Invoice / Document Automation | Complete | documents.py, database.py, runtime.py, server.py, ui/jarvis.js | 84 Python tests; real local PDF generation; invoice and report browser flows; probe 26/26; launch.cmd | 169d50e | None |
| 22 Deep H.O.L.O Context | Complete | core/context.py, runtime.py, ui/jarvis.js, galaxy.js | 86 Python tests; note/card/node events; expiry and metadata boundary tests; browser context acceptance; probe 26/26; camera-free launch | a73081a | None |
| 23 Full Agent / Tool Registry | Complete foundation | tools.py, orchestrator.py, runtime.py | 88 Python tests; 38 typed definitions; argument, permission, unavailable, error, and verification tests; probe 26/26; browser + launch green | SHA in `../FINAL_HANDOFF.md` | Approval ledger is Phase 24 |
| 24 Permission + Approval Engine | Complete | approvals.py, database.py, runtime.py, tools.py, orchestrator.py, ui/jarvis.js | Expiring pending ledger, exact-argument grant, reject/expire states and redacted preview; registered writes, Gmail send and Calendar mutations require approval; unit/HTTP/browser validation | SHA in `../FINAL_HANDOFF.md` | None |
| 25 Persistent Visual Cards | Complete | cards.py, database.py, runtime.py, ui/jarvis.js/css | 98 Python tests; 11 supported card types; explicit save, bounded payload, restart restore, pin/dismiss/remove; browser invoice card save/restore; probe 26/26 and camera-free launch | SHA in `../FINAL_HANDOFF.md` | None |
| 26 Integrations / Settings Panel | Complete foundation | core/runtime.py, ui/jarvis.js/css, docs/SETUP.md | 98 Python tests; 12 safe status rows and DB/index diagnostics; browser status panel; no credential exposure or hardware prompt; probe 26/26 and camera-free launch | SHA in `../FINAL_HANDOFF.md` | Live provider/device diagnostics require local setup |
| 27 Safe Windows Computer Control | Complete safe adapter; live Windows acceptance pending | windows.py, core/runtime.py, core/orchestrator.py, tools.py | 103 Python tests; allowlisted app/file/public URL, path traversal and script guard, foreground mocks, volume mock, typed approvals and natural-language browser flow; probe 26/26; camera-free launch | SHA in `../FINAL_HANDOFF.md` | Physical Windows active-window/audio test; screenshot remains one-shot browser chooser |
| 28 Offline / Degraded Mode | Complete | tests/test_degraded_mode.py, core/runtime.py, docs/SETUP.md | 105 Python tests; network-blocked startup, Astra/embedding/vision/Gmail/Calendar/Telegram disabled, local note search + graph and clear status; camera-free browser and launch validation | SHA in `../FINAL_HANDOFF.md` | None |
| 29 Privacy Hardening | Complete foundation | security.py, ui/jarvis.js/css, Telegram, vision, Context | 106 Python tests; secret formats redacted, global mute stops mocked active recognition and blocks voice/wake; transient audio/image flows and visible indicators reviewed; browser acceptance zero page errors, probe 26/26 | SHA in `../FINAL_HANDOFF.md` | Physical microphone release test remains pending |

## Phase 19 continuation checkpoint

This continuation began at `07e086e9cebfbb3ad20f3908c24251ba8554c9e5`,
with a clean working tree. It added an opt-in personal-memory panel and
search/inspect/update/forget API on the existing source-backed SQLite schema.
Explicit saves reject secret-like values and non-user provenance. Narrow
first-person significance rules may capture profile, preference, project,
decision, workflow, person, and task facts; conversations and provider content
are not bulk-saved. Retrieval marks personal memories separately from indexed
notes. Schema migration, HTTP, orchestrator, provenance, and text-safe UI tests
are included. Phase 19 was committed as `1c71e9bb2b792e65ea2215457fb88c86a1e51b6f`.

The browser acceptance harness now runs with Playwright installed in the ignored
local `node_modules` folder. Test endpoints mock remote Telegram/document
actions; Python tests use mocked bot transport and real locally generated PDFs.
No Telegram token or provider key was supplied.

## Full checkpoint SHAs

- Baseline: `278fe99f44907a4af3db2e9d3aacfb144970625d`
- Audit: `63285c72dc96ee48edde1c1fb7bfde1900ef6da4`
- Runtime/state: `fc7431371898ce82b7abfe91f4adb751a76f1319`
- Memory: `f2aa1f890dfef9bffba0b99ad5b35dd5be4b1178`
- Retrieval/brain: `03815eda290930929e79d89077b70004b29aa3e1`
- HOLO/galaxy: `ba9a4875fd2aae283d5db7156f3a936835c43419`
- Live research: `45719c8f17fc93a884d11aaa788eeb1a98047344`
- Browser voice: `780f1cca7b8a366fe1c805b662736f8b51fb299c`
- Opt-in wake: `ef50b56cabca4e24664c9dc1641566dd62a792da`
- Phase 12 spoken interruption: `1cdad6ac3bd193ddbe322b8dc2d75d9eb6d58ede`
- Phase 13 screen vision: `77cfd8e618b29a22bdc2deae127d47c022748ad1`
- Phase 14 Jarvis Eyes: `e9037200b3d13e2b0e6f8be95a71fbc363e932ef`
- Phase 15 Focus Lock: `5c52c3c2b7881e91c410cd508e009b1f60b4456f`
- Phase 16 Gmail: `dbde0592551981b85acb495727f6d1bc1cb3e1bb`
- Phase 17 Calendar: `eda74d3e5ec80552adfb9ca344e5b6f171cf985c`
- Phase 18 Morning briefing: `38d6d7030054b62cb2d295f13740ea1b35367c01`
- Phase 19 Long-term Memory: `1c71e9bb2b792e65ea2215457fb88c86a1e51b6f`
- Phase 20 Telegram Remote Jarvis: `0c483dc097ae30d408512ea6214c2c5df663f34a`
- Phase 21 Invoice / Document Automation: final SHA recorded in the sibling `../FINAL_HANDOFF.md`.

## Final validation

- Python 3.11 project environment: Phase 22 **86/86**; Phase 23 **88/88 tests passed**.
- Actual OpenAI SDK 2.54.0 serialization/parsing tested over mocked HTTP.
- Actual pypdf 6.19.0 extraction tested with generated PDF text.
- `pip check` green; compilation and diff whitespace checks green.
- Original HOLO probe **26/26**, both props loaded.
- Browser acceptance: simulation hands, camera-free startup, search/graph focus,
  source reader, selected summaries, follow-ups, expand/collapse, typing isolation,
  mocked voice transcript, reindex, narrow viewport, research offline state and
  mocked temporary-card controls, interim and final speech recognition, listening
  cancellation, opt-in wake command, spoken interruption and mute, echo and
  wake suppression during playback, wake resume, denied/unavailable speech.
  One-shot screen chooser, indicator, transient JPEG request, immediate track
  release, denied sharing, one-shot camera frame, track disposal, missing/denied
  camera states, Focus Lock controls and natural-language start, unchanged memory
  document count; Gmail mocked read/search/thread/summary/draft/reply/send flows;
  Calendar mocked today/tomorrow/search/availability and confirmed create,
  reschedule and cancel; briefing integration data, safe text rendering, manual
  button and natural-language invocation, and no automatic startup request;
  personal memory create/search/provenance/edit/forget; Telegram disabled state;
  invoice details and PDF preview; document pin, share approval/revocation and
  dismissal; report creation; selected-note context restoration and graph
  node-collapse context. **Zero page errors.**
- Windows `launch.cmd` started `server.py`; health endpoint and browser acceptance
+  passed on isolated port 64117 with temporary data.
- Phase 20 commit: `0c483dc097ae30d408512ea6214c2c5df663f34a`.
- Phase 21 commit: `169d50e08a14823622d2a586035eb688054944ef`.
- Phase 22 commit: `a73081a40c8cdffec16f732a635d729746b90a97`.
- Phase 23 completed and committed; exact SHA is recorded in the sibling `../FINAL_HANDOFF.md`.
- Sample index: eight documents/chunks/entities/edges; no extraction errors.
- No key/live API call, microphone recording, webcam test or external message.
- vendor/, props/ and sample-notes/ unchanged. Private runtime data remain ignored.

## Exact continuation point

Phases 0–29 are complete. Continue at Phase 30 — Automation Engine,
using the Phase 27 commit recorded in the sibling `../FINAL_HANDOFF.md` as the
checkpoint. Preserve Phases 0–28 and do not restart or redesign them.

The only pending checks require the user's own accounts or physical hardware:
Telegram bot token and user allowlist; optional OpenAI key for voice-note
transcription; Gmail/Calendar OAuth; physical microphone/acoustic echo; live
screen vision; physical webcam; and live Windows foreground-app monitoring.
Configure credentials locally only; never request them in chat.

## Known limits

No native py launcher was discoverable in this session; use launch.cmd here.
The source entry point remains Python-compatible, but native `py server.py`
cannot be claimed verified until the system launcher is available.

Vector search scans active chunks; large-vault performance is not benchmarked.
Graph view is bounded to 300 nodes, with focused search outside the first page.
Edges are explicit MENTIONS with evidence, not inferred semantic facts. Summaries
above 80k characters visibly declare partial coverage. Reindex is startup/manual.
Deleted sources retain local tombstoned history; personal-memory forget is
implemented with a source tombstone. Browser voice may be online and requires local hardware
acceptance. Browser recognition supplies interim text and endpointing; dedicated
VAD and real microphone/acoustic echo acceptance remain pending. The video
could not be retrieved; validation uses the supplied written specification.

The exact final delivery SHA is recorded in the sibling `../FINAL_HANDOFF.md`
after the final commit, avoiding a self-referential commit hash. `git rev-parse
HEAD` is authoritative. All validated source and documentation are committed.
