---
name: python-project-engineering
description: Write, refactor, and review Python application code in school-reminders using practical SOLID design, explicit types, reliable boundaries, and the project's offline validation workflow.
---

# Python engineering for school-reminders

Read root AGENTS.md, pyproject.toml, relevant code/tests, and PROJECT_PLAN.md before
changing behavior. Use the companion python-design-patterns and python-code-style
skills as references. This project's instructions govern conflicting examples.

## Architecture and SOLID

- Single responsibility: keep CLI parsing/presentation, OAuth/Gmail I/O, MIME
  decoding, domain extraction, and persistence cohesive and independently testable.
  Split by reasons to change, not one class per file or an arbitrary line count.
- Open/closed: introduce an extension point when a real second implementation or
  requirement justifies it. An injected function is often sufficient for a strategy.
- Liskov substitution: implementations must preserve documented inputs, outputs,
  failure behavior, and side effects. Test shared behavioral contracts when adding
  an alternative implementation; do not strengthen preconditions in subclasses.
- Interface segregation: expose only operations a consumer needs. Prefer small
  typing.Protocol interfaces at meaningful boundaries over a broad Gmail-shaped
  interface leaking vendor types throughout the application.
- Dependency inversion: domain rules must not depend on argparse, Google clients,
  filesystem paths, or a database driver. Pass required collaborators explicitly;
  wire concrete adapters at the application entry point. Avoid service locators
  and mutable global clients.

Prefer functions, data classes, and composition. Use Adapter for vendor isolation,
Strategy for interchangeable extraction behavior, or Repository for actual storage
needs when justified. Do not add empty repositories, factories, abstract base
classes, inheritance hierarchies, or dependency-injection frameworks speculatively.
Describe the concrete coupling or duplication a proposed pattern resolves.

## Python and dependency choices

- Preserve the declared Python 3.10 minimum unless explicitly changing support.
  Use built-in collection annotations, X | None, pathlib, context managers,
  dataclasses for value objects, and collections.abc for abstract collection types.
  Do not copy Python 3.12-only type statement or generic parameter syntax.
- Annotate public functions and significant boundaries, including returns. Model
  external payloads using TypedDict or convert them into validated domain values.
  Confine Any to unavoidable dynamic library edges; do not silence typing errors
  with broad ignores or casts that conceal missing validation.
- Separate pure transformations from I/O. Validate external data at entry points,
  avoid mutable defaults, and preserve semantic differences between absent, empty,
  invalid, and unknown values. Use explicit units and timezone-aware datetimes
  when resolving instants; preserve original email date values separately.
- Follow PEP 8 and PEP 257. Document contracts, side effects, units, evidence
  provenance, and failure modes when they are not clear from names and types.
- Prefer standard-library tools already fitting the job (email, argparse,
  dataclasses, json, zoneinfo, unittest). Check maintained official documentation
  and Python compatibility before adding a third-party dependency. Record the
  concrete need and dependency in pyproject.toml; do not add a framework merely
  because a skill example uses it. Retain the supported Google client libraries.
- Catch specific actionable errors at appropriate boundaries; preserve causes
  with raise ... from error when translating exceptions. Never silently suppress
  failures. Use resource context managers; define bounded timeouts/retries for
  network operations, retrying only safe transient failures.
- Avoid logging credentials, tokens, raw emails, or private evidence. Preserve
  original MIME and Gmail IDs; normalized text is derived data. Re-read root
  privacy and extraction invariants before touching those boundaries.

## Validation and review

Before refactoring, identify behavior to preserve and add focused regression
coverage for changed contracts. Use synthetic messages and injected transports;
keep unit tests offline in tests/unit/. Test observable behavior, errors, pagination,
and evidence preservation where relevant rather than private implementation shape.
Use unittest and unittest.mock; upstream pytest examples are illustrative only.

Run with the project's interpreter (on Windows, .venv/Scripts/python.exe if needed):

```sh
python -m pip install -e .
python -m unittest discover -s tests/unit -v
git diff --check
```

If adding lint/format/type tooling, configure it in pyproject.toml for Python 3.10,
put it in optional development dependencies, and run it before claiming enforcement.
Ruff and mypy are suitable options; their presence in a skill does not mean they
are installed or passing. Adopt stronger checks with a reviewed migration rather
than hiding existing failures. Do not replace the test runner incidentally.

Review module dependency direction, failure paths, compatibility, and sensitive
data handling. Report offline checks separately from explicitly authorized live
Gmail verification. Keep README.md and PROJECT_PLAN.md accurate; skill installation
alone does not refactor or certify existing application code.

## Authoritative references

Consult these for the specific feature being changed, using version-appropriate
documentation rather than copying a skill's example blindly:

- [PEP 8](https://peps.python.org/pep-0008/) and [PEP 257](https://peps.python.org/pep-0257/)
- [Python 3.10 library reference](https://docs.python.org/3.10/library/)
- [Typing specification](https://typing.python.org/en/latest/spec/)
- [Python packaging guide](https://packaging.python.org/en/latest/)
- [Gmail API reference](https://developers.google.com/workspace/gmail/api/reference/rest)
- [Ruff documentation](https://docs.astral.sh/ruff/) and [mypy documentation](https://mypy.readthedocs.io/)
