# School Reminders

Read school emails from a configured Gmail sender and extract notices with Groq.
Activity dates, storage, and delivery are tracked in [PROJECT_PLAN.md](PROJECT_PLAN.md).

## Requirements

- Python 3.10 or newer

## Setup

Create a virtual environment from the project folder:

```sh
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or on macOS/Linux:

```sh
source .venv/bin/activate
```

Install the package and its Google API dependencies:

```sh
python -m pip install -e .
```

## Gmail authorization

Follow the [Google Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python):
enable the Gmail API in a Google Cloud project, configure OAuth consent (add your
account as a test user if using testing mode), and create a **Desktop app** OAuth
client. Download its JSON to `.secrets/credentials.json`.

The first run opens browser sign-in and saves a reusable token to `.secrets/token.json`.
The `gmail.readonly` scope cannot change or send mail. It permits mailbox reading;
the sender restriction is enforced by this application, not Google's permission.
Testing-mode OAuth apps may require periodic reauthorization.

## Run

```sh
python -m school_reminders --sender school@example.com --limit 20 --output data/emails.json
```

## Project structure

```text
school-reminders/
├── src/school_reminders/  # CLI, OAuth, and Gmail reader
├── tests/unit/           # Offline tests
├── AGENTS.md             # Coding instructions
├── PROJECT_PLAN.md       # Implementation milestones
├── pyproject.toml   # Project metadata
├── README.md        # Setup and usage
└── .gitignore       # Files excluded from Git
```

Application responsibilities are organized as follows:

```text
src/school_reminders/
├── cli.py
├── domain/
│   ├── __init__.py
│   └── email_message.py  # Email value object
├── email/
│   ├── __init__.py
│   ├── auth.py           # OAuth and token persistence
│   ├── gmail.py          # Gmail requests and sender filtering
│   └── mime.py           # Pure MIME parsing
└── gmail.py              # Compatibility imports for original callers
```

The CLI handles arguments, JSON export, and presentation. Domain classes do not
depend on Gmail transport, OAuth, or the CLI.

Replace the example sender with the school's exact address. The installed
`school-reminders` command accepts the same options. Credential paths are relative
to the working directory; override using `--credentials PATH` and `--token PATH`.

The reader follows result pages and verifies the From address. Archived and read
mail are included; spam and trash are excluded. It prints dates, subjects, and IDs.
Optional JSON exports preserve Gmail IDs, the original Date header, receipt timestamp,
plain text, HTML, and original MIME content as base64url. Attachments are retained
in raw MIME but not analyzed. HTML-derived text is separate from original content.
Repeated runs reread emails; deduplication will be added with storage.

Keep credentials and emails private. `.secrets/` and `data/` are ignored by Git;
custom output paths need their own ignore rules.

## Classify notices by audience

Classification returns scheduled appointments and school events with an explicit
calendar day and month in the email or newsletter. The export includes the original
date wording in `event_date` and an exact source reference in `date_evidence`.
Undated appeals, standalone deadlines, and relative-only dates such as “next Friday”
are outside this filter. Repeated instructions for one appointment belong in one entry.
Audience evidence is limited to two short phrases naming the intended recipients.
If Groq supplies extra citations, the reader verifies them and keeps the first
two distinct source spans in each evidence list.
Dated theme days and optional dress-up days are included. A date such as
“Monday 16th November” retains its weekday and ordinal when quoted from the source.
For Sway newsletters, the reader also checks for dated, named day headings
immediately followed by an explicit invitation to all pupils or families at school.

```powershell
python -m school_reminders --sender info@parentmail.co.uk --limit 3 --classify --output data/notices.json
```

Save your Groq key in `.secrets/.env` in the project folder:

```dotenv
GROQ_API_KEY=your_key_here
```

Replace the placeholder with the key from your Groq Free organization. Run commands
from the project folder. Git ignores this file. A key supplied in the environment
takes precedence. The command above sends each subject, body and linked Sway newsletter text together to
`openai/gpt-oss-120b` using LangChain's `ChatGroq` integration in `GroqNoticeModel`. Groq applies the
quota and billing plan of the key's organization. The app supplies the 2026–27
roster shown below. Ordinary Gmail reads without `--classify` use Gmail only.
As each email is classified, the terminal shows its original date and subject,
then each notice title and its assigned audience. Uncertain audiences are marked
for review, and an email with no notices is labelled accordingly.

| Year group | Classes |
| --- | --- |
| Reception (EYFS / Foundation) | Ash, Beech |
| Year 1 | Chestnut, Damson |
| Year 2 | Elm, Fig |
| Year 3 | Holly, Juniper |
| Year 4 | Maple, Oak |
| Year 5 | Pine, Rowan |
| Year 6 | Silver Birch, Willow |

The request contains the subject and HTML text nodes, or the plain-text body
when HTML is absent. Gmail IDs, raw MIME, attachments and HTML attributes stay
local. The notice list links back to its exported email. Each notice includes
a title, audience, exact evidence quotes and source offsets. The application
checks quotes against the decoded source and checks labels against the roster.
Unclear audiences carry a review flag. These checks establish that quotes exist;
the model still interprets what they mean. If a quote fails verification or an
assigned audience lacks evidence, the app asks Groq once to correct that email.
A failed request or unresolved validation error
leaves the previous report intact.

If Groq rejects the request size or reaches its output token limit, the reader
processes smaller portions and combines the verified notices in source order.
An explicit context-length error also triggers splitting. If Groq rejects its
own generated JSON, the app retries once. Other HTTP 400 failures report the
provider error code and request ID when supplied.
For long newsletters, Groq selects numbered source passages and the reader copies
the selected text directly. Short newsletters also use this fallback if a quote
still fails verification after correction.
When passage selection returns an event without an audience citation, the app
clears the proposed recipients and flags the audience for review. The event
still requires verified activity and date evidence.
Evidence offsets still refer to the original email or newsletter snapshot.

During classification, the reader follows direct public Microsoft Sway links in the
email and reads each newsletter once, even if the thumbnail, title and button all
link to it. It includes the newsletter title, text cards and available image
descriptions. The private export stores each newsletter's URL and retrieved text
under `newsletters`. A citation with source `newsletter_1` uses offsets into
`newsletters.newsletter_1.text`. An unreadable Sway fails the scan so an incomplete
newsletter cannot be reported as having no notices. Image-only text, video/audio,
attachments and the contents of onward links are outside the current reader's coverage.

### Parse email content or a Sway URL from Python

In PyCharm, open the project-root `run_notices.py`, edit `EMAIL_CONTENT` and
optionally `EMAIL_SUBJECT`, then run the file. Set `EMAIL_IS_HTML = True` for an
HTML body. To process a newsletter directly, fill in `SWAY_URL`. Clear it to
switch back to the email. The Run window displays the notices. Keep real school
content and private newsletter links out of commits.

With `GROQ_API_KEY` configured, call `parse_notices` directly from Python.
The helper runs independently of Gmail, the JSON export and email delivery.

```python
from school_reminders.extraction import parse_notices

report = parse_notices("Oak class will visit the museum on 12 May.", subject="Class trip")
for notice in report["notices"]:
    print(notice["title"], notice["audience"], notice["evidence"])

# With a public newsletter URL copied from an email
newsletter_report = parse_notices(sway_url)
```

Pass `html=True` for an HTML body. Both input forms return a dictionary with
`notices` and `newsletters`. The latter holds any linked source snapshots.
An empty notice list means the model found no notices. Input, retrieval and
model validation errors raise `ValueError`.

To test the model with a synthetic mixed-audience email after setting your key:

```sh
python -m unittest discover -s tests/integration -p test_groq_live.py -v
```

Run offline tests after installation:

```sh
python -m unittest discover -s tests/unit -v
```

## Email the completed scan

Append the following settings to the existing private `.secrets/.env`:

```dotenv
EMAIL_ENABLED=true
EMAIL_FROM=your-sending-account@gmail.com
EMAIL_TO=your-recipient@example.com
SMTP_PASSWORD=your-app-password
```

For Gmail, enable 2-Step Verification on the sending account and generate an
[app password](https://support.google.com/accounts/answer/185833) if your account
supports it. Enter it without the display spaces. The defaults are
`SMTP_HOST=smtp.gmail.com` and `SMTP_PORT=465`. Another provider can be used
with its implicit-TLS host and port, using the sender address as the login.
Environment variables take precedence over the file. Gmail scanning continues
to use its separate read-only OAuth credentials.

Run the usual scan command. After the scan and any requested export finish, the
app sends one plain-text email with the count, dates, and subjects. Classified
scans include notice titles and audience labels. Empty scans send a zero count.
A failed scan or export skips delivery. An SMTP failure returns an error and
preserves the export. Rerunning a successful scan sends a fresh digest.
Set `EMAIL_ENABLED=false` to disable sending.

## Daily digest on GitHub Actions

The **Daily school digest** workflow runs at **07:17 Europe/London** and emails
one digest for the previous London calendar day. It includes every matching
message's date and subject, including a zero-count report on quiet days.
Gmail receipt time determines which day a message belongs to.

1. Complete Gmail authorization locally using the steps above. In the private
   GitHub repository, open **Settings → Secrets and variables → Actions**.
2. Under **Secrets**, create `GMAIL_TOKEN_JSON` with the complete contents of
   the authorized `.secrets/token.json` (including its refresh token). Add
   `EMAIL_FROM`, `EMAIL_TO` and `SMTP_PASSWORD` as separate secrets using the
   SMTP settings above. If Google revokes the grant, authorize locally again
   and replace the token secret.
3. Under **Variables**, set `SCHOOL_SENDER` to the school's exact From address.
   Optionally set `SMTP_HOST` and `SMTP_PORT` for another implicit-TLS provider.
   To include extracted notice titles and audiences, set `CLASSIFY_NOTICES` to
   `true` and add a `GROQ_API_KEY` secret. This opts in to sending the subject,
   body and linked Sway newsletter text to Groq on each run.
4. Enable Actions and merge the workflow and application changes into the
   default branch. For a first delivery, open **Actions → Daily school digest →
   Run workflow**. Leave the date blank for yesterday or enter a missed day
   as `YYYY-MM-DD`. Each successful invocation sends a digest, so check your
   inbox before repeating a date. Missed days require manual backfill.

The runner discards the temporary OAuth token and any classified export.
The delivery step reports success or failure and keeps private mail out of
the Actions log. GitHub may delay scheduled runs under load.
[GitHub schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## Python development guidance

Repository skills in [.agents/skills](.agents/skills/) cover practical SOLID
principles, design patterns, Python style, typing, library choices, and validation.
[AGENTS.md](AGENTS.md) routes Python work through the project engineering skill.
The two community skills come from
[wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/python-development/skills);
see [provenance and local policy](.agents/skills/UPSTREAM.md).
You can explicitly request `$python-project-engineering`, `$python-design-patterns`,
or `$python-code-style`. Newly installed skills are available on the next turn.

These instructions preserve Python 3.10 support and unittest. Ruff and mypy are
recommended options, not installed or enforced checks. Adding skills does not
automatically enforce checks. The application has been refactored using these
skills while retaining its CLI options, export fields, and OAuth behavior.
