# Implementation plan

Development guidance: repository Python skills are installed under `.agents/skills/`
and routed from AGENTS.md. They cover SOLID, patterns, style, typing, and validation;
application responsibilities now separate CLI, OAuth, Gmail I/O, and MIME parsing.
Email integration lives in `email/`; domain value objects live in `domain/`.
Linting and static type-checking enforcement remain future development tooling work.
The refactor preserves CLI/export contracts and current interactive authorization
behavior; non-interactive server authorization remains future work. Tests were
left unchanged and not run for this refactor at the user's request.

## 1. Gmail reading — implemented, live verification pending

- [x] Establish src package layout and command-line interface.
- [x] Implement read-only desktop OAuth and local token reuse.
- [x] Filter by sender, verify From address, paginate, and limit results.
- [x] Extract MIME text/HTML and retain original content and email identifiers.
- [x] Support optional private JSON export and offline tests.
- [ ] Obtain exact school sender address from user.
- [ ] Configure local Google OAuth credentials and authorize Gmail access.
- [ ] Verify a small live batch, including HTML, against the mailbox.

Acceptance: retrieve matching emails with source evidence without modifying mail.

## 2. Identify Year 4 relevance

- [ ] Agree rules for Year 4/Y4, class names, whole-school activities, and mixed-year messages.
- [ ] Decide scope for attachments, newsletters, forwarded content, and linked documents.
- [ ] Extract relevant sections with exact source quotes; flag ambiguous cases for review.
- [ ] Validate inclusion/exclusion using synthetic and locally reviewed examples.

## 3. Extract activities

- [ ] Define title, description, class/year, location, event dates, deadlines,
  parent actions, evidence quotes, and source references.
- [ ] Support multiple activities per email and unknown dates.
- [ ] Resolve relative dates from email context; use Europe/London for school times.
- [ ] Distinguish receipt dates, event dates, and action deadlines.
- [ ] Choose deterministic extraction or an explicitly approved AI service.

## 4. Database storage

- [ ] Agree database choice; SQLite is an option for a local application.
- [ ] Store source emails separately from linked activities, retaining original
  content, Gmail message/thread IDs, receipt dates, activity dates, and evidence.
- [ ] Add migrations and idempotent ingestion keyed by Gmail message ID.
- [ ] Handle duplicate announcements, corrections, rescheduling, and cancellation.
- [ ] Agree retention and backups.

## 5. Reminders and operation

- [ ] Agree delivery channel and reminder timing.
- [ ] Add scheduled ingestion, incremental checkpoints, retries, and error reporting.
- [ ] Prevent duplicate reminders; provide review for uncertain activities.
- [ ] Add explicitly invoked integration tests and deployment instructions.

Immediate inputs: school sender address and local OAuth configuration.
Later inputs: child's class name if needed, whole-school relevance rules,
attachment scope, database, delivery channel, and reminder schedule.
