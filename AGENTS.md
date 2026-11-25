# AGENTS.md

Instructions for AI coding agents working on **family-bot**: a modular Discord bot for a Grand RP family
(reminders, finance ledger, inventory logs, quests, bonus requests, solar, diplomacy, events).
Read `PLAN.md` first for architecture, data model, and roadmap. If this file and `PLAN.md` conflict, ask the user.

## Stack
Python 3.12+, `uv`, `discord.py` 2.x, PostgreSQL 16, SQLAlchemy 2.0 async, Alembic, `pydantic-settings`,
`structlog`, `pytest` + `pytest-asyncio`, `ruff`, `pyright`, Docker Compose.

## Commands
```bash
uv sync                                   # install deps
uv run python -m familybot                # run bot
uv run ruff check . && uv run ruff format .
uv run pyright
uv run pytest                             # all tests
uv run pytest tests/unit -q               # fast tests
uv run alembic revision --autogenerate -m "<message>"
uv run alembic upgrade head
docker compose up -d --build              # bot + postgres
```
Before declaring any task done: `ruff check`, `pyright`, and `pytest` must pass.

## Architecture rules (non-negotiable)
1. **Layers:** `modules/<name>/cog.py` → `service.py` → `db/repositories/`. Dependencies point downward only.
2. **Cogs are thin:** parse input, call a service, format output. No business logic, no SQL.
3. **Services never import `discord`.** They take and return plain dataclasses/DTOs and raise `AppError` subclasses.
4. **Only repositories touch SQLAlchemy sessions.** One session per interaction, committed in the service layer.
5. **Scheduler talks to Discord only through the `Notifier` protocol** so it can be faked in tests.
6. **Modules are self-contained.** Adding a feature must not require editing other modules. Shared code lives in `core/`.
7. **Money and stock are append-only.** Never UPDATE or DELETE `ledger_entries` / `inventory_moves`. Corrections are new reversing rows. Balance and stock are derived with SUM.
8. **Every state change writes an `audit_log` row** (actor, action, entity, payload, correlation id).
9. **No hard-coded game values** (timer durations, battery limits, role names, channel IDs). Read them from `guild_settings`.

## Module template
```
modules/<name>/
  cog.py       # slash commands only
  service.py   # business logic
  views.py     # buttons/modals/selects
  schemas.py   # DTOs
```
Also add: `db/models/<name>.py`, `db/repositories/<name>.py`, an Alembic migration, and tests in
`tests/unit/` (service, no DB) and `tests/integration/` (service + Postgres).
Cogs are auto-loaded from `modules/*/cog.py`. Do not hand-register them.

## Code conventions
- Fully typed. No `Any` unless unavoidable (comment why). Use `from __future__ import annotations`.
- Async everywhere on I/O. Never block the event loop (no `requests`, no `time.sleep`, no sync DB calls).
- Store all datetimes as **timezone-aware UTC**. Convert to the guild timezone only at the display edge (`core/time.py`).
- Money and counts are **integers** (no floats).
- Use `structlog` (`log = structlog.get_logger()`), structured key/values, never `print`.
- User-facing failures: raise `AppError` (safe message). Unexpected exceptions: let the global handler log them and show an error ref.
- Small functions, explicit names, no clever metaprogramming. Prefer boring code.
- Comments explain *why*, not *what*.

## Discord rules
- Slash commands only (grouped via `app_commands.Group`). No prefix commands.
- Respond or `defer()` within 3 seconds. Any DB or network work → defer first.
- Personal or error replies are `ephemeral=True`. Shared-state changes are public embeds **and** a post to the configured log channel.
- Persistent Views: `timeout=None`, `custom_id` prefixed `"<module>:<action>:<id>"`, re-registered in `setup_hook`. Handlers must be idempotent (double click must not double-apply).
- Destructive actions require a confirm button.
- Permission checks for money/approval actions go in the **service** layer (not only a cog decorator).
- Set `allowed_mentions` explicitly; never allow `@everyone`. Role pings only from the scheduler for configured roles.
- Minimal intents. Do not enable message content or presences.
- Use autocomplete for item names, categories, and members where possible.
- Embed styling comes from `core/embeds.py`. Do not hand-roll colors/footers.

## Scheduler rules
- Reminders are **rows in `reminders`**, not in-memory tasks. Never use `asyncio.sleep` for long timers or `tasks.loop` per reminder.
- Claim due rows with `SELECT ... FOR UPDATE SKIP LOCKED`. Must be safe with 2+ bot instances.
- Retries with exponential backoff; after max attempts mark `failed` and alert the error channel.
- Firing must be idempotent: a reminder fires once even across crashes/restarts.

## Database rules
- Every schema change = Alembic migration. Never edit applied migrations; add a new one.
- Migrations must be reversible where practical and reviewed by hand after autogenerate.
- Index foreign keys and `(status, due_at)` on `reminders`.
- Use transactions for multi-row changes (e.g. bonus approval + ledger entry). Use idempotency keys (`ref_id`) to avoid duplicates.

## Testing
- Services: unit tests with fake repositories/notifier. No Discord, no network.
- Repositories and scheduler: integration tests against real Postgres (testcontainers or compose service). Never mock the DB for these.
- Every new service function: happy path + at least one failure path (permissions, negative stock, duplicate request).
- Bug fix = failing test first, then the fix.

## Observability
- Each interaction gets a correlation id (contextvar) attached to every log line, audit row, and user-facing error ref.
- Log at `INFO` for state changes, `WARNING` for recoverable problems, `ERROR` with traceback for failures.
- Never log tokens, secrets, or full DB URLs.
- `/admin status` and `/healthz` must keep working. Don't break them.

## Security
- Secrets only from env/`.env` (never committed). Update `.env.example` when adding a variable.
- Validate and bound all user input (amounts > 0, max lengths, enum choices).
- Do not add dependencies without a clear reason; pin via `uv add` (updates `uv.lock`).

## Git & PRs
- Small, focused commits. Conventional style: `feat(finance): add transfer command`.
- One module/feature per branch. Include migration + tests in the same PR.
- Update `PLAN.md` if architecture or data model changes.

## Definition of done
- [ ] Follows layering rules above
- [ ] Types pass (`pyright`), lint passes (`ruff`)
- [ ] Tests added and passing
- [ ] Migration included (if schema changed) and `alembic upgrade head` works on a fresh DB
- [ ] Audit log written for every state change
- [ ] Logs use structlog with correlation id
- [ ] No hard-coded game values or IDs
- [ ] `.env.example` and `PLAN.md` updated if needed

## Do not
- Put logic in cogs or import `discord` in services.
- UPDATE/DELETE ledger or inventory rows.
- Use floats for money, naive datetimes, or `print`.
- Use in-memory timers for reminders.
- Hard-code Grand RP timings, role names, or channel IDs.
- Skip migrations or edit existing ones.
- Add a "cluster"/sharding layer, Redis, or a message queue unless the user asks (the design is cluster-ready already).

## Current focus
Follow the phases in `PLAN.md` §7 in order. Do not start a later phase until the earlier phase's "done when" criteria pass.
