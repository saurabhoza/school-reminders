# Implementation plan

## Progress as of 22 November 2026

Milestone 1 is complete. All five offline tests passed, covering
sender verification and pagination, plain-text source preservation, HTML fallback,
invalid input, and an empty mailbox.

The live read-only check retrieved three messages from the confirmed sender.
All three contained HTML and readable text. For each message, the original MIME,
thread ID, and receipt timestamp matched a second Gmail read by message ID.

Milestone 2 now uses Groq for whole-email notice extraction. The earlier
passage-by-passage classifier was retired. Offline tests cover Gmail reading,
extraction with a simulated Groq endpoint, and the per-email classification display.
The three-message live check above verified Gmail. A separate live Groq test
on synthetic text retained two dated events and omitted an undated book appeal.

Development guidance: repository Python skills are installed under `.agents/skills/`
and routed from AGENTS.md. They cover SOLID, patterns, style, typing, and validation;
application responsibilities now separate CLI, OAuth, Gmail I/O, and MIME parsing.
Email integration lives in `email/`; domain value objects live in `domain/`.
Linting and static type-checking enforcement remain future development tooling work.
The refactor preserves CLI/export contracts and current interactive authorization
behavior. The daily workflow refreshes a locally authorized token unattended.

## 1. Gmail reading — complete

- [x] Establish src package layout and command-line interface.
- [x] Implement read-only desktop OAuth and local token reuse.
- [x] Filter by sender, verify From address, paginate, and limit results.
- [x] Extract MIME text/HTML and retain original content and email identifiers.
- [x] Support optional private JSON export and offline tests.
- [x] Confirm the exact sender with the user (`info@parentmail.co.uk`).
- [x] Confirm the default local credential and token files are present.
- [x] Verify read-only Gmail access with the local OAuth configuration.
- [x] Verify a small live batch, including HTML, against the mailbox.

Acceptance: retrieve matching emails with source evidence without modifying mail.

## 2. Extract notices with Groq — implemented, live verification pending

- [x] Use the supplied 2026–27 Reception to Year 6 roster and whole-school category.
- [x] Read direct public Microsoft Sway newsletters during classification and retain cited text snapshots.
- [x] Expose verified extraction as a Python helper for pasted email bodies or standalone Sway URLs.
- [ ] Decide scope for attachments, media, forwarded content, and other linked documents.
- [x] Use LangChain's `ChatGroq` integration in `GroqNoticeModel` and strict structured output with
  `openai/gpt-oss-120b`. Extraction starts with the whole message and linked Sway text,
  then splits the source if Groq reports an input or output size limit.
- [x] Check the returned roster labels and exact supporting quotes locally.
- [x] Display each classified email's date and subject with the audience for each notice.
  Keep the original email and its Gmail references with the extracted notices.
- [x] Test the LangChain request, mixed notices, ambiguity, invalid quotes, and export failures offline.
- [x] Label source segments explicitly and retry an evidence failure once for the affected email.
- [x] Retain verified Sway events with missing audience citations and mark their recipients as unclear.
- [x] Accept weekday-prefixed ordinal dates and include optional participation days.
- [x] Run the synthetic live Groq test for dated events and audience assignments.
- [ ] Evaluate mixed-year newsletters for missed events and incorrect date or audience assignments.

## 3. Extract activities

- [ ] Define title, description, class/year, location, event dates, deadlines,
  parent actions, evidence quotes, and source references.
- [x] Extract scheduled events with a source-backed calendar day and month, skip
  undated requests, and limit audience evidence to short phrases.
- [ ] Resolve relative dates from email context; use Europe/London for school times.
- [ ] Distinguish receipt dates, event dates, and action deadlines.
- [x] Select Groq for notice extraction.

## 4. Database storage

- [ ] Agree database choice; SQLite is an option for a local application.
- [ ] Store source emails separately from linked activities, retaining original
  content, Gmail message/thread IDs, receipt dates, activity dates, and evidence.
- [ ] Add migrations and idempotent ingestion keyed by Gmail message ID.
- [ ] Handle duplicate announcements, corrections, rescheduling, and cancellation.
- [ ] Agree retention and backups.

## 5. Reminders and operation

The daily digest workflow targets a private GitHub repository with a standard
Linux Actions runner. It is scheduled for 07:17 Europe/London on the default
branch and supports manual backfill by receipt date. Five minutes
per day is about 155 runner minutes in a 31-day month. Confirm available account
allowance and spending controls before enabling the workflow.
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

- [x] Implement unattended read-only Gmail OAuth, Actions secret inputs, private
  logging and SMTP digest delivery for the previous London calendar day.
- [ ] Configure repository secrets and verify the first hosted delivery.
- [x] Show scan progress and per-email counts. Enable detailed subject, date and Groq response logs in the daily workflow.
- [ ] Persist checkpoints and sent-reminder IDs outside the temporary runner.
  Catch up after delayed or missed runs, and ensure retries do not send duplicates.
- [ ] Test a scheduled synthetic run and a repeated run before enabling live mail.

- [x] Send one plain-text email digest after a completed scan and requested export.
  The SMTP sender and recipient are configured separately from read-only Gmail OAuth.
- [ ] Verify live delivery with the configured sender and recipient.
- [ ] Agree event reminder timing.
- [ ] Add incremental checkpoints and safe automated catch-up after missed runs.
- [ ] Prevent duplicate reminders; provide review for uncertain activities.
- [ ] Add explicitly invoked integration tests and deployment instructions.

Next, verify Groq on synthetic notices. Attachment and other linked-document handling,
durable storage, and event reminder timing remain open decisions.
