# CLAUDE.md

Guidance for AI assistants (Claude Code and similar tools) working in this repository.

## Status

This repository is currently empty — no source code has been committed yet. The sections below are a template. As the project takes shape, update each section so it reflects the actual code and workflows. Delete this "Status" section once the project is bootstrapped.

## Project Overview

**Name:** Hyatt-checker

**Purpose:** _TBD — likely a tool for checking Hyatt hotel availability, award nights, points pricing, or related reservation data. Replace this paragraph with a one-sentence description of what the tool actually does once decided._

**Primary use case:** _TBD_ (e.g., CLI script run on a schedule, web service, browser extension, notification bot).

## Repository Structure

Once code lands, document the top-level layout here. Example shape to fill in:

```
.
├── src/                # Application source
├── tests/              # Test suite
├── scripts/            # One-off scripts and tooling
├── .github/workflows/  # CI definitions
└── CLAUDE.md           # This file
```

Keep this section current — when a new top-level directory is added, add a one-line description here.

## Tech Stack

Document the chosen stack here when picked. Examples to record:

- **Language & runtime:** _TBD_ (e.g., Python 3.12, Node 20, Go 1.22)
- **Package manager:** _TBD_ (e.g., `uv`, `pip`, `npm`, `pnpm`)
- **Key libraries:** _TBD_ (HTTP client, scraping/automation, scheduler, notification provider)
- **Storage:** _TBD_ (SQLite, JSON file, none)
- **Hosting:** _TBD_ (local cron, GitHub Actions, serverless, container)

## Development Workflow

Fill in once tooling exists. Suggested commands to document:

```bash
# Install dependencies
# e.g., uv sync   |   npm install

# Run the app locally
# e.g., python -m hyatt_checker   |   npm run start

# Run tests
# e.g., pytest   |   npm test

# Lint / format
# e.g., ruff check . && ruff format .   |   npm run lint
```

Update these once the real commands are in place. Prefer documenting the exact command a contributor should run, not a generic description.

## Branching & Commits

- Default branch: `main` (once initialized).
- Feature work happens on branches named `claude/<slug>` (for AI-driven sessions) or `<user>/<slug>`.
- Open a PR against `main`; do not push directly.
- Keep commits focused; one logical change per commit. Write the "why" in the message, not just the "what".

## Conventions

Populate these as the codebase establishes patterns. Examples to capture:

- **Code style:** which formatter/linter and any project-specific rules.
- **Type checking:** whether types are required, and how strict.
- **Testing:** what to test (unit vs. integration), where tests live, naming.
- **Logging:** logger to use, log levels, what should/shouldn't be logged.
- **Secrets:** how API keys and credentials are loaded (env vars, `.env`, secret manager). Never commit secrets.
- **External APIs:** rate-limit and retry policy when calling Hyatt or third-party endpoints; respect robots.txt and ToS if scraping.

## Things AI Assistants Should Know

- This is a personal project; favor small, readable code over heavy abstraction.
- Don't add features the task didn't ask for, and don't introduce frameworks or dependencies without checking with the maintainer.
- When making web requests against Hyatt or other live services, be conservative with request volume during development — avoid hammering production endpoints.
- Don't commit credentials, cookies, session tokens, or personally identifying reservation data. If example data is needed in tests, use clearly fake values.
- Update this file when the project structure, stack, or workflow changes meaningfully.

## Open Questions

Track decisions that haven't been made yet:

- [ ] What does "checking" mean here — award availability, cash rates, both?
- [ ] How does the tool authenticate (logged-in session, public endpoints only)?
- [ ] How are results delivered — stdout, email, Slack/Discord, push notification?
- [ ] How often does it run, and where (laptop cron, GitHub Actions, hosted)?

Resolve these and either move the answers into the relevant section above or delete the question.
