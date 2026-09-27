# JARVIS build progress — Phase 18 checkpoint, 2026-09-27

Branch: `jarvis-second-brain`.
User-specified run start SHA: `b50ed173704f95c994f540c9ebab8649082517bf`.
Recovered checkpoint before this continuation: `22cd05567d030183bc10aae2d8d9d6e4c24416eb`.
The original archive on D: is unchanged.

Phases 0–9 foundation are implemented and automatically validated. Live cloud and
physical microphone acceptance remain pending. This is not complete video parity.

## Phase status, files, validation and remaining work

| Phase | Status | Main files | Validation | Commit | Remaining |
|---|---|---|---|---|---|
| 0 Audit | Complete, host launcher caveat | BASELINE_AUDIT.md | Probe 26/26, sim, root, tree, state POST | 278fe99, 63285c7 | Native py absent from tool PATH; launch.cmd verified |
| 1 Runtime | Complete | core/runtime.py, server.py | HTTP tests, actual restart | fc74313 | None |
| 2 State machine | Complete foundation | core/state.py, context.py, ui/jarvis.js | State paths, isolation, voice lifecycle | fc74313, ba9a487 | Spoken interruption remains in Phase 12 |
| 3 Second brain | Complete foundation | memory/database.py, graph.py | Provenance FKs, evidence, active-only graph | f2aa1f8 | Long-term memory workflows are Phase 19 |
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
| 18 Morning briefing | Complete code/mocks/UI, OAuth user setup required for live data | briefing.py, runtime.py, ui/jarvis.js, H.O.L.O briefing card | 55 Python tests; disconnected/failure fallbacks, source-backed brain inputs, mock integrations, manual-only card/voice; browser acceptance and probe 26/26 | pending | Optional Google OAuth setup for live Gmail and Calendar inputs |
| 19–31 | Not started as phases | MASTER_SPEC.md | None claimed | — | Later integrations and memory workflows |

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

## Final validation

- Python 3.11 project environment: **55/55 tests passed, zero skips**.
- Actual OpenAI SDK 2.54.0 serialization/parsing tested over mocked HTTP.
- Actual pypdf 6.19.0 extraction tested with generated PDF text.
- `pip check` green; compilation and diff whitespace checks green.
- Original HOLO probe **before 26/26; after 26/26**, both props loaded.
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
  button and natural-language invocation, and no automatic startup request.
  **Zero page errors.**
- Windows launch.cmd successfully started server.py at http://localhost:4900 for Gmail
  http://localhost:4901 for Calendar and http://localhost:4902 for the briefing.
- Sample index: eight documents/chunks/entities/edges; no extraction errors.
- No key/live API call, microphone recording, webcam test or external message.
- vendor/, props/ and sample-notes/ unchanged. Private runtime data remain ignored.

## Exact continuation point for a lower-cost model

1. Read SETUP.md and ARCHITECTURE.md. Launch local sample mode; run the Python
   tests and tests/browser.cjs. Do not rewrite the existing UI or gesture engine.
2. When credentials are authorized, verify an Astra selected-note summary with
   citations, semantic paraphrase after explicit vector indexing, and actual
   microphone transcript search independent of the camera. Record results without
   secrets or private source bodies. Mocks do not prove live account access.
3. **Next coding task: Phase 19, Long-term Memory.** Add intentional memory
   workflows over the existing source-backed schema: remember, retrieve, explain
   provenance, and forget. Never save every conversation automatically.
4. Gmail and Calendar remain NOT CONNECTED until OAuth is configured locally as
   described in SETUP.md; never request secrets in chat.

## Known limits

No native py launcher was discoverable in this session; use launch.cmd here.
The source entry point remains Python-compatible, but native `py server.py`
cannot be claimed verified until the system launcher is available.

Vector search scans active chunks; large-vault performance is not benchmarked.
Graph view is bounded to 300 nodes, with focused search outside the first page.
Edges are explicit MENTIONS with evidence, not inferred semantic facts. Summaries
above 80k characters visibly declare partial coverage. Reindex is startup/manual.
Deleted sources retain local tombstoned history; explicit purge belongs with the
future forget workflow. Browser voice may be online and requires local hardware
acceptance. Browser recognition supplies interim text and endpointing; dedicated
VAD and real microphone/acoustic echo acceptance remain pending. The video
could not be retrieved; validation uses the supplied written specification.

The exact final delivery SHA is recorded in the sibling `../FINAL_HANDOFF.md`
after the final commit, avoiding a self-referential commit hash. `git rev-parse
HEAD` is authoritative. All validated source and documentation are committed.
