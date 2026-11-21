# Implementation plan

## Progress as of 21 November 2026

Milestone 1 is complete. All five offline tests passed, covering
sender verification and pagination, plain-text source preservation, HTML fallback,
invalid input, and an empty mailbox.

The live read-only check retrieved three messages from the confirmed sender.
All three contained HTML and readable text. For each message, the original MIME,
thread ID, and receipt timestamp matched a second Gmail read by message ID.

Milestone 2 now uses Groq for whole-email notice extraction. The earlier
passage-by-passage classifier was retired. Nine offline tests pass, including
four extraction tests with synthetic email and a simulated Groq endpoint.
The three-message live check above verified Gmail only. Live Groq accuracy
is pending a free-tier API key and a synthetic pilot.

Development guidance: repository Python skills are installed under `.agents/skills/`
and routed from AGENTS.md. They cover SOLID, patterns, style, typing, and validation;
application responsibilities now separate CLI, OAuth, Gmail I/O, and MIME parsing.
Email integration lives in `email/`; domain value objects live in `domain/`.
Linting and static type-checking enforcement remain future development tooling work.
The refactor preserves CLI/export contracts and current interactive authorization
behavior; non-interactive server authorization remains future work.

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
- [ ] Decide scope for attachments, newsletters, forwarded content, and linked documents.
- [x] Use LangChain's `ChatGroq` integration in `GroqNoticeModel` and strict structured output with
  `openai/gpt-oss-120b`. One request covers the subject and body of one message.
- [x] Check the returned roster labels and exact supporting quotes locally.
  Keep the original email and its Gmail references with the extracted notices.
- [x] Test the LangChain request, mixed notices, ambiguity, invalid quotes, and export failures offline.
- [ ] Run the synthetic live Groq test with a Free organization key, then evaluate
  mixed-year newsletters for missed notices, incorrect audiences and misleading evidence.

## 3. Extract activities

- [ ] Define title, description, class/year, location, event dates, deadlines,
  parent actions, evidence quotes, and source references.
- [ ] Support multiple activities per email and unknown dates.
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

Planned host: a private GitHub repository with a standard Linux Actions runner.
Schedule one daily run on the default branch, away from the top of the hour
(proposed 07:17 Europe/London), plus a manual trigger for retries. Five minutes
per day is about 155 runner minutes in a 31-day month. Confirm available account
allowance and spending controls before enabling the workflow.
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

- [ ] Configure read-only Gmail OAuth for unattended use, put credentials and
  the Groq key in Actions secrets, and keep private message details out of logs.
- [ ] Persist checkpoints and sent-reminder IDs outside the temporary runner.
  Catch up after delayed or missed runs, and ensure retries do not send duplicates.
- [ ] Test a scheduled synthetic run and a repeated run before enabling live mail.

- [ ] Agree delivery channel and reminder timing.
- [ ] Add scheduled ingestion, incremental checkpoints, retries, and error reporting.
- [ ] Prevent duplicate reminders; provide review for uncertain activities.
- [ ] Add explicitly invoked integration tests and deployment instructions.

Next, verify Groq on synthetic notices. Attachment and linked-document handling,
durable storage, and the reminder delivery channel remain open decisions.
