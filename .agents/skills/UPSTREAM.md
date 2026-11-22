# Skill provenance and local policy

Installed on 2026-11-15 using the bundled skill installer, Git transport, from
the `main` branch of https://github.com/wshobson/agents (a moving upstream ref):

- `python-design-patterns`: `plugins/python-development/skills/python-design-patterns`
- `python-code-style`: `plugins/python-development/skills/python-code-style`

These are community guidance, not an official Python standard or an endorsement
by the Python Software Foundation. Upstream files and bundled references are
retained as downloaded. Their MIT license is in THIRD_PARTY_LICENSE.txt.

`python-project-engineering` is locally authored for this repository. Root
AGENTS.md and that skill resolve differences from upstream examples: Python
3.10 compatibility, unittest, existing packaging, privacy, and proportionate
abstractions. Ruff/mypy are recommendations, not configured quality gates.
Related upstream skills linked by the downloaded skills are not installed;
use the local engineering skill and official documentation for those topics.

Review future upstream changes before replacing these files. Installation does
not execute the examples or authorize dependencies, live mail access, or refactors.
