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

## Gmail (Phase 16)

The Gmail card is opt-in and shows **NOT CONNECTED** until local Google OAuth
credentials are configured. The adapter reads inbox/unread/search results and
threads on demand, makes a local extractive summary, and creates drafts. Sending
is a separate action: Jarvis asks for browser confirmation and the server also
requires the exact phrase `SEND <draft-id>`. Mail content is treated as untrusted,
is not added to the second brain, and is not persisted by this adapter.

To connect it locally:

1. In Google Cloud, create/select a project, enable the Gmail API, configure its
   OAuth consent screen, and create an OAuth client for a local installed or web
   application. Request only `https://www.googleapis.com/auth/gmail.readonly`,
   `https://www.googleapis.com/auth/gmail.compose`,
   `https://www.googleapis.com/auth/gmail.send`,
   `https://www.googleapis.com/auth/calendar.events.readonly`,
   `https://www.googleapis.com/auth/calendar.events.freebusy`, and
   `https://www.googleapis.com/auth/calendar.events`. Google may require
   consent-screen verification or test-user approval for these scopes. See the
   [Gmail scope list](https://developers.google.com/workspace/gmail/api/auth/scopes)
   and [Calendar scope list](https://developers.google.com/identity/protocols/oauth2/scopes).
2. Use Google's OAuth flow outside chat with offline access to obtain a refresh
   token for the intended account and these scopes. Keep the client secret and
   refresh token private; never paste them into chat or commit them.
3. Set `JARVIS_GOOGLE_CLIENT_ID`, `JARVIS_GOOGLE_CLIENT_SECRET`, and
   `JARVIS_GOOGLE_REFRESH_TOKEN` in the local process environment, then restart
   `launch.cmd` and press Refresh in the Gmail card. Credentials are read from
   the process environment; Jarvis does not provide a credential-entry page.

Without those local values, Gmail and Calendar remain disconnected and their
controls stay disabled. Automated tests use a mocked Google token endpoint and
mocked provider APIs; they do not send real email or modify events.

## Google Calendar (Phase 17)

The Calendar card reads today, tomorrow, a selected time range, event search, and
free/busy information on demand. Create, reschedule and cancel each show a browser
confirmation, then the server checks the exact action phrase. Jarvis reports a
change as complete only after Google confirms it. Events remain in Google and are
not copied into the local second brain. The three Calendar scopes above are the
least-privilege scopes used for these read, availability and event operations.

The Morning Briefing card runs only when pressed or requested with “give me my
morning briefing.” It includes connected Calendar and Gmail information, local
priorities, active tasks, deadline/reminder notes, recent projects and the Focus
target. Gmail and Calendar may remain disconnected; local items still appear.
Read-aloud remains governed by the existing opt-in voice checkbox. There is no
startup speech or background schedule.

## Personal long-term memory (Phase 19)

Personal Memory is local to the Jarvis data directory. Use “remember that …”
for an explicit save, or open the Personal Memory panel to search, inspect its
provenance, edit, or forget an item. Jarvis captures only a narrow set of clear
first-person facts and preferences; it does not save every conversation,
research result, email, calendar item, or screen. Secret-like values are
rejected. Saved facts can be surfaced in answers as personal memory, separate
from indexed notes. No extra credentials are required.

## Telegram Remote Jarvis (Phase 20)

Telegram is off until configured and started from the local UI. Create a bot
using Telegram's official BotFather flow, then set `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_ALLOWED_USER_IDS` (comma-separated numeric account IDs), and
`JARVIS_TELEGRAM_ENABLED=1` in the local process environment. Restart Jarvis,
review the allowed-user count, then press **Start remote Jarvis**. Only private
messages from allowlisted IDs are handled. Press **Stop remote Jarvis** to end
polling. The token is never shown in the UI or returned by the status route.
Do not put bot tokens in chat, source files, notes, or screenshots.

Voice notes are downloaded in memory, capped at 10 MB, transcribed only when a
local OpenAI key is configured, and discarded after the reply. Telegram does
not access the H.O.L.O camera or activate browser microphone listening. Generated
file sharing requires both local approval on the document card and an exact
`SHARE <document-id>` reply in Telegram; files outside Jarvis's generated
document registry are never eligible.

## Invoice and document PDFs (Phase 21)

Install project dependencies using `requirements-lock.txt`. The **New invoice**
card collects seller and customer names/addresses, line-item description,
quantity, currency and unit price before generating anything. Tax is optional
and is never inferred. A natural-language request such as “Create an invoice for
Company X for ₹25,000 for app development” fills the customer, amount and item,
then asks for missing business and customer details before PDF creation. The
invoice is rendered locally with a unique invoice number and stored under the
Jarvis data directory's `generated` folder. Reports, summaries and letters use
the same PDF renderer; the currently selected indexed note is recorded as a
source when one is selected.

Every generated PDF card offers preview/open, save a copy, pin and dismiss.
Telegram sharing is off by default and requires local approval plus in-chat
confirmation. No invoice, report, summary or letter is sent automatically.
