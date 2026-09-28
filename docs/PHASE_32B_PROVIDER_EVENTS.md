# Phase 32b — Provider-event automation scope

Status: implementation and mocked validation complete; live Gmail and
Calendar firing remains **USER ACTION REQUIRED**. This scope extends the Phase
30 automation hook already present in `docs/MASTER_SPEC.md` and
`docs/ARCHITECTURE.md`; it does not add new provider events or automation
actions.

## Specification boundary

The only provider events are Gmail `IMPORTANT_EMAIL` and Calendar
`CALENDAR_APPROACHING`. Actions remain the existing local notification,
morning-briefing preparation, and active-focus check. Provider data is read-only
input and cannot send mail, change Calendar, invoke a tool, create an approval,
or authorize any operation. Existing approval gates are unchanged.

Each provider source has an independent local enable control in **Local
Automations**. Both start disabled. An enabled source is inert unless its
provider is configured and at least one matching automation rule is enabled.
The source state is visible in the automation panel and Integrations / Settings.
Changing a source control does not call a provider; live reads occur only on the
background scheduler.

## Polling and event behavior

- The existing background scheduler checks provider sources at most once every
  five minutes. It starts no additional worker or retry loop. A provider call
  uses the existing adapter's bounded request timeout and runs off the request
  handler, so local search, chat and H.O.L.O remain available.
- Gmail reads only the first 50 IDs matching `in:inbox is:important
  newer_than:90d`. It makes no per-message detail request; subjects, snippets,
  sender details and bodies are not passed to automation rules.
- Calendar reads at most 250 events, within the largest enabled rule horizon
  (0–1440 minutes). `minutes_before` means “fire once when the event is within
  this many minutes”; a rule with no value uses 60 minutes. Cancelled, past,
  invalid and out-of-window events are ignored. Only event ID and start time
  contribute to the private identity fingerprint; title, location, description
  and attendees are not used.
- The first successful check establishes a quiet baseline for already-present
  Gmail messages and already-due Calendar rule windows. This avoids an initial
  burst of notices. Later qualifying events use persistent content-free
  SHA-256 receipts to suppress repeats across polling cycles and restarts.
- Receipts expire after 90 days and the table is capped at 5,000 newest rows.
  Run history and transient notices contain only provider/event labels and the
  opaque fingerprint, not raw provider IDs or payloads.
- A missing OAuth configuration causes no transport call. Provider failures
  expose a generic error state, retain no exception/payload, and retry only on
  the next bounded interval. Disabling a source prevents subsequent polls and
  rechecks enablement before dispatching results from a read already in flight.

## Verification boundary

Automated tests use fake adapters and cover opt-in state, disconnected mode,
provider failures, quiet baselines, threshold behavior, duplicate suppression,
restart persistence, provenance fingerprints, and the absence of provider
write/approval paths. These tests do not validate live OAuth, provider scopes,
account data, or real notification timing. Follow `docs/LIVE_ACCEPTANCE.md` for
separate live checks when the user has configured the relevant account. Do not
report live acceptance complete based on mocks.
