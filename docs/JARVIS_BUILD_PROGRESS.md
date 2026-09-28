# JARVIS build progress — Gemini provider continuation, 2026-09-28

Branch: `jarvis-second-brain`.
Phase 22–31 run start SHA: `169d50e08a14823622d2a586035eb688054944ef`.
Phase 21 foundation checkpoint: `169d50e08a14823622d2a586035eb688054944ef`.
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
| 29 Privacy Hardening | Complete foundation | security.py, ui/jarvis.js/css, Telegram, vision, Context | 106 Python tests; secret formats redacted, global mute stops mocked active recognition and blocks voice/wake; transient audio/image flows and visible indicators reviewed; browser acceptance zero page errors, probe 26/26 | a13abdb | Physical microphone release test remains pending |
| 30 Automation Engine | Complete, including Phase 32b opt-in provider sources; live source acceptance pending | automations.py, provider_events.py, memory/database.py, integrations, runtime.py, server.py, ui/jarvis.js/css | Provider-specific opt-in, five-minute bounded polling, quiet baseline, threshold rules, content-free dedupe receipts, safe status, mocks and browser controls | Phase 32b checkpoint below | Live Gmail/Calendar event firing remains pending |
| 31 Full System Hardening + Video-Parity Acceptance | Complete written-spec acceptance; live devices/providers pending | security.py, automations.py, memory/long_term.py, tests | 116 Python tests; malicious note/PDF/email/provider content stays data, screen instructions remain untrusted, Telegram allowlist, path and approval expiry checks, shared secret detector; browser zero page errors; launch/simulation/camera-free; probe 26/26 | recorded in `../FINAL_HANDOFF.md` | Authorized live APIs and physical devices require user setup |

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

Phases 0–31 are complete. This requested continuation stops here. Preserve the
validated repository; await the user's Phase 32 specification before continuing.

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

## Phase 32a checkpoint — Live Acceptance Runbook (documentation only), 2026-09-28

Docs-only checkpoint, committed on top of the unchanged Phase 31 code baseline
`f8d6077`.

- Added `docs/LIVE_ACCEPTANCE.md`: the Phase 32a runbook separating three
  validation tiers — (A) mocked tests (already green), (B) live credential
  tests (OpenAI, Gmail OAuth, Calendar OAuth, Telegram), and (C) physical
  hardware tests (microphone wake/interruption/echo/mute release, webcam
  Jarvis Eyes, live screen capture + vision, Windows foreground monitoring /
  Focus Lock) — each with the exact existing command or test to re-run and
  explicit pass criteria and negative gate checks.
- `docs/MASTER_SPEC.md` was verified to exist and is referenced (not modified)
  as the acceptance-form target for the user's live pass.
- **No production code changed.** No .py, .js, HTML, runtime, integration,
  security, automation or UI file was touched. No packages were installed and
  no credentials or secrets were added. Validation was performed with the
  existing local suite only.
- **Live acceptance is still pending and must not be reported complete.**
  Every Tier B (live credential) and Tier C (physical hardware) item in the
  runbook remains unexecuted; they require the user's own accounts and devices,
  configured locally per `docs/SETUP.md`. The Phase 31 pending list is
  unchanged: Telegram token/allowlist, optional OpenAI key, Gmail/Calendar
  OAuth, microphone/acoustic echo, live screen vision, physical webcam, and
  live Windows foreground monitoring.
- At this checkpoint the next task was to await live acceptance or a Phase 32b
  specification. The user supplied the Phase 32b request; that work is recorded
  below.

## Phase 32b checkpoint — Provider-event automation

Phase 32b implements the requested Gmail `IMPORTANT_EMAIL` and Calendar
`CALENDAR_APPROACHING` sources using the existing adapters, automation rules,
runtime and scheduler. Each source is off by default and separately enabled in
Local Automations. Polling is read-only, checks no more than every five minutes,
and runs in the existing bounded background scheduler. A source remains inert
when disconnected or when it has no enabled matching rule. Initial successful
checks establish a quiet baseline; hashed event-identity receipts are bounded
to 90 days and 5,000 rows. Raw email/calendar content is not persisted or used
as permission authority. Source state is shown in Local Automations and
Integrations / Settings.

- Scope and threat boundaries: `docs/PHASE_32B_PROVIDER_EVENTS.md`.
- Local configuration and baseline behavior: `docs/SETUP.md`.
- Live event checks are documented separately in `docs/LIVE_ACCEPTANCE.md` and
  remain pending until actually exercised with the user's Google account.
- Phase 32b automated validation: **126 Python tests + 27 subtests passed**;
  browser acceptance passed with probe 26/26, both props and zero page errors.
  `launch.cmd` started camera-free/microphone-free local mode; `pip check`,
  Python compilation, JavaScript syntax and `git diff --check` passed. No live
  provider, hardware or Astra behavior is implied by mocked validation.
- Next task: user-side Tier B/C live acceptance from the runbook for configured
  accounts/devices. No additional implementation phase is defined by
  `docs/MASTER_SPEC.md` after Phase 31; do not invent unrelated code work.

## Phase 31 final acceptance — 2026-09-28

- Run started at Phase 21 SHA `169d50e08a14823622d2a586035eb688054944ef`;
  Phase 30 checkpoint was `6a6ebcfefe961cb4892f3f1da7773f55d9fb010e`.
- Python: **116/116 passed**. Original H.O.L.O probe: **26/26** with both props.
- Browser acceptance: PASS, zero page errors; tested simulation, camera-free
  startup, context, source-backed chat, cards, settings, local automation CRUD,
  approvals, mocked Gmail/Calendar, invoice/document, voice interruption/wake/
  mute, transient screen/camera paths, Focus Lock and responsive viewport.
- `launch.cmd`: PASS on an isolated port and temporary data. Health reports local
  mode, `camera_required=false`, `microphone_required=false`; simulation and probe
  routes return HTTP 200. `pip check`, Python compile, JavaScript syntax and Git
  whitespace checks pass.
- Security review: retrieval, web research, email, generated/indexed PDF and
  screen content remain untrusted data; no content-derived approval or shell
  execution; Telegram sender allowlist enforced; Windows paths and public URLs
  constrained; expired approvals do not execute; secret detector/redactor covers
  supported OpenAI, Google, GitHub, bearer, Telegram and credential-assignment
  forms. No live provider write was performed.
- Isolated 1,000-note benchmark: index/startup 1.37 s, local search 107 ms,
  focused graph 12 ms on this host. This is a synthetic local measurement, not a
  large production-vault guarantee.
- Exact Phase 31 SHA is in the sibling `../FINAL_HANDOFF.md`. No Phase 32 task was
  supplied; stop after this checkpoint.

## Gemini provider checkpoint — 2026-09-28

Run starts at Phase 32b commit `fa68e2296187dced2e7e9b34ea0d2888547e0130`.
This continuation adds Gemini as an explicit live provider behind the existing
Astra contract. It uses the direct Google `generateContent` REST API because
the prior implementation depends on OpenAI Responses-only schema and response
fields; Gemini is not treated as a Responses-compatible endpoint. The selected
documented stable Free Tier model is `gemini-3.8-flash`, configurable with
`GEMINI_MODEL`. `AI_PROVIDER=gemini` and `GEMINI_API_KEY` are required; Gemini
failure stays on local extractive fallback and never switches to another
external provider. The existing OpenAI contract remains available separately.

Gemini answer JSON is validated against the current local source IDs, URLs are
removed, credential-shaped values are redacted, and no model tools or action
authority are provided. The same selected provider handles explicit one-shot
screen/camera analysis and bounded Telegram voice-note transcription using
inline image/audio data; frames and audio are not persisted or sent via the
Gemini Files API. A pytest startup guard forces automated suites to offline mode
even if a developer has credentials configured. The setup docs call out the
Free Tier data-use policy and advise against sending confidential material.

- Code: **implemented**. Mocked validation: **138 Python tests + 27 subtests**;
  focused AI/security/regression selection: **52 passed + 10 subtests**.
- Browser acceptance: **26/26 probe checks**, both props loaded, zero page
  errors; simulation and camera-free/microphone-free behavior passed.
- `launch.cmd`, `pip check`, Python compilation, JavaScript syntax and
  `git diff --check`: passed.
- Live Gemini API/authentication: **pending**. `GEMINI_API_KEY` was not
  configured in this run, so no live call was made. Live source-grounded answer,
  live screen image analysis and live Telegram audio transcription remain
  unverified. Physical microphone, webcam and display acceptance also remain
  separate user checks.
- Exact next task: when ready, configure the key locally (never in chat) and
  run the Gemini Tier B steps in `docs/LIVE_ACCEPTANCE.md`. Do not mark mocked
  results as live provider or physical-device acceptance. No unrelated code
  feature is the next task.

## Gemini live chat request fix — 2026-09-28

Run starts at `cb32e4a986b7f6db7b377d086a54c01379cfbf52`. A sanitized local
diagnostic reproduced a provider HTTP 400 `INVALID_ARGUMENT` on the Astra
structured request using the configured `gemini-3.5-flash-lite` model. The
provider error identified the `additionalProperties` schema hint as unsupported
for that deployment. A temporary diagnostic read only the error category/status
and request/response shape; it did not print the key or raw provider body and
was removed before commit. Replaying the same request after omitting that
provider-only hint succeeded and returned a valid citation.

The Gemini adapter now omits `additionalProperties` recursively from wire
schemas. Astra, vision and voice transcription enforce exact allowed response
keys locally, preserving the closed application contract. Orchestration routes
only conservative self-contained arithmetic and short conversational phrases
to AI without note evidence; unrelated selected/retrieved note text is omitted
from those requests. Other unsupported factual questions remain source-gated,
and source-backed answers still require real local source IDs.

- Live text: **passed** with locally configured `gemini-3.5-flash-lite`.
  “What is 2+2?” returned a Gemini-mode answer ending in 4 with no note
  citations. A selected-source summary of a temporary synthetic note returned
  Gemini-mode output and the exact selected document ID as its citation. No
  personal note text was sent in this check.
- Mocked regression: **141 Python tests + 27 subtests passed**; focused
  Gemini/Astra/grounding/security/approval/degraded/vision/Telegram/HTTP set:
  **65 passed + 5 subtests**. Browser: H.O.L.O probe **26/26**, both props,
  zero page errors. `launch.cmd` started offline with camera and microphone
  optional; `pip check`, Python compilation, JS syntax and diff checks passed.
- Diagnostics captured no API key in stdout/stderr. Existing transient image
  and audio handling is unchanged; their tests remain green. Live vision,
  Telegram transcription, webcam, microphone and other provider/hardware
  acceptance remain separately pending.
- Exact next task: continue only the remaining live acceptance in
  `docs/LIVE_ACCEPTANCE.md` when the user's corresponding credential or hardware
  is available; no additional Gemini chat implementation is pending.
