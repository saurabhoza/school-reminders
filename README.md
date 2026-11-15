# School Reminders

Read school emails from a configured Gmail sender. Year 4 activity extraction and
database storage are planned in [PROJECT_PLAN.md](PROJECT_PLAN.md).

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

Application responsibilities are separated into `cli.py` (arguments, export, and
presentation), `auth.py` (OAuth and token persistence), `gmail.py` (Gmail requests
and sender filtering), and `messages.py` (email values and pure MIME parsing).
Existing imports from `gmail.py` remain available for compatibility.

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
custom output paths need their own ignore rules. No classification, database,
scheduling, or reminders are implemented yet.

Run offline tests after installation:

```sh
python -m unittest discover -s tests/unit -v
```

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
