# instructions

- A repository for Worqueue (ワーキュー): a task manager for a player-manager that shows priorities across their own work and the work they hand to the team. Operated through a CLI (with JSON output for agents) and viewed in a local web UI.
- Always respond in Japanese.
- `docs/spec.md` holds design decisions (with their reasons) and verified facts. Read the relevant sections before changing code.
  - When you are making a change on a branch and a decision is made or a fact is verified (including measurement results), update `docs/spec.md` in the same change.
  - For investigation, questions, or review requests, do NOT edit `docs/spec.md`. Report findings in your reply (or an Issue comment) instead.
- This repository is in development (0.x); backward compatibility is NOT required.
  - NEVER add or keep compatibility layers, deprecated aliases, or re-exports for old import paths.
  - Exception: once the CLI's JSON output is decided in `docs/spec.md`, agents rely on it. Change it only together with `docs/spec.md`.
- Coding rules for every language (keeping the code easy to change): [.agents/docs/coding.md](.agents/docs/coding.md)

## Working tree

- NEVER edit, create, or delete tracked files on the local `main` branch unless the user explicitly asks for that edit on `main`.
  - Investigation-only requests are read-only: no file edits at all, except scratch files under `tmp/<task-name>/`.
  - If a code or doc change seems necessary, propose it and wait for instructions, or create a branch or worktree first.

## Python

- Always use `uv run -m`.
- NEVER use `python -m`.
- Coding rules: [.agents/docs/python.md](.agents/docs/python.md)
- Running tests: [.agents/docs/pytest.md](.agents/docs/pytest.md)

### Verification commands

- Run lint: `uv run -m ruff check .`
- Run tests: `uv run -m pytest --tb=short -q`

## Github

- Commit: [.agents/docs/commit.md](.agents/docs/commit.md)

## Temporary files

- Create all temporary scripts and investigation files under `tmp/<task-name>/` at the repository root (one subdirectory per task), never directly in `tmp/`.
- When the task is complete, delete only the files you created, then the empty `tmp/<task-name>/` with `rmdir`. NEVER delete `tmp/` itself or other subdirectories: other agents may be using them.
