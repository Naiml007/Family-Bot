# PLAN.md — TheSnow Discord Bot

> Step-by-step execution strategy derived from [agents.md](./agents.md).
> Disposable working doc: update status as you go.

## 0. Metadata
- **Objective:** Refactor the monolithic bot into a modular, tested, secure, async, and event-driven system.
- **Source spec:** [agents.md](./agents.md)
- **Owner (role):** Architect + Implementer
- **Status:** COMPLETED
- **Last updated:** 2026-11-27

## 1. Scope
- **In scope:** Project tooling, configuration and logging, authorization fixes, core extraction, feature modularization, async DB, event-driven scheduling, security hardening, tests and CI.
- **Out of scope / non-goals:** Postgres migration, managed hosting changes, and unrelated gameplay-content changes.
- **Assumptions & constraints:** Preserve existing Discord commands and panel behavior; SQLite remains the initial database; feature modules can be shipped incrementally; no secrets may be committed.

## 2. Milestones
| # | Milestone | Exit criterion | Status |
|---|-----------|----------------|--------|
| M1 | Safety net | Tooling, logging, config validation, global errors, and authorization fixes ship without panel behavior regressions | DONE |
| M2 | Core extraction | Async database, migrations, permissions, forms, embeds, scheduler, and app context exist | DONE |
| M3 | Feature modules | Existing panels and commands are registered through feature extensions | DONE |
| M4 | Performance | Async DB, batch queries, cache, publish queue, and bounded Discord retries are active | DONE |
| M5 | Idle efficiency | Fixed 20-second ticker is replaced by deadline-driven scheduling | DONE |
| M6 | Hardening and verification | Security findings, tests, and static checks are complete | DONE |

## 3. Phased Execution

### Phase 0 — Safety net (no behavior change)
- [x] Step 0.1 — Add `pyproject.toml`, pinned dependencies, ruff/mypy/pytest configuration, and test directories · owner: Implementer · verify: `python -m pytest`
- [x] Step 0.2 — Add `.env.example` and typed, fail-fast Discord token/Guild configuration · owner: Implementer · verify: missing required config exits with a clear error
- [x] Step 0.3 — Configure structured logging and global interaction/tree error handling · owner: Implementer · verify: bot startup and command-error tests
- [x] Step 0.4 — Re-check administrator/roles in server-side authorization; add denial coverage · owner: Implementer · verify: authorization unit tests
- [x] Step 0.5 — Replace scheduler startup print and ready print with logging · owner: Implementer · verify: no production `print` calls
- **Exit gate:** Existing bot behavior remains usable; lint/types/tests pass.

### Phase 1 — Core extraction
- [x] Step 1.1 — Create `thesnow/core/database.py` and `migrations.py` with versioned migrations, WAL, and indexes · owner: Implementer · verify: empty-to-latest integration test
- [x] Step 1.2 — Extract permissions, forms, embeds, errors, and logging from globals · owner: Implementer · verify: unit tests
- [x] Step 1.3 — Add `AppContext` composition and a thin async DB interface · owner: Implementer · verify: feature smoke tests
- [x] Step 1.4 — Add event-driven scheduler skeleton and deadline computation · owner: Implementer · verify: scheduling unit tests
- **Exit gate:** Core modules have no feature-module imports and Discord I/O is isolated.

### Phase 2 — Feature modules
- [x] Step 2.1 — Move balance and seeds into `features/*/` extensions · owner: Implementer · verify: existing interaction tests pass
- [x] Step 2.2 — Move remaining features and persistent panels to feature setup functions · owner: Implementer · verify: command and panel regression tests
- [x] Step 2.3 — Remove `BUILDERS`, `VIEWS`, `ACTIVE`, and feature-global `db/bot` dependencies · owner: Implementer · verify: no module-global bot/db registries
- **Exit gate:** `main.py` is the only wiring root and every feature has setup/service/panel boundaries.

### Phase 3 — Performance
- [x] Step 3.1 — Replace synchronous DB access with the async facade · owner: Implementer · verify: integration and interaction tests
- [x] Step 3.2 — Remove N+1 queries and add per-guild config caching · owner: Implementer · verify: query-count tests
- [x] Step 3.3 — Add bounded Discord retries and async publish queue · owner: Implementer · verify: retry/failure tests
- **Exit gate:** No synchronous DB calls remain in async handlers.

### Phase 4 — Resource efficiency
- [x] Step 4.1 — Replace the 20-second ticker with a computed-next-deadline task · owner: Implementer · verify: scheduler tests
- [x] Step 4.2 — Add mutation wakeups and per-alert re-ping scheduling · owner: Implementer · verify: scheduling integration tests
- [x] Step 4.3 — Convert delete-and-repost panel updates to coalescing in-place `get_partial_message` edits · owner: Implementer · verify: panel update tests
- **Exit gate:** Steady state sleeps until the next persisted deadline.

### Phase 5 — Hardening and tests
- [x] Step 5.1 — Close URL, rate-limit, ticket, reaction, and guild allowlist findings · owner: Implementer · verify: security-focused tests
- [x] Step 5.2 — Reach core/shared coverage ≥ 90% with unit and integration tests · owner: Implementer · verify: `pytest --cov`
- [x] Step 5.3 — Verify ruff, strict mypy, and pytest across the codebase · owner: Implementer · verify: `ruff`, `mypy`, `pytest` green
- **Exit gate:** All acceptance criteria are green.

## 4. Dependencies (ordering)
```
Phase 0 ─▶ Phase 1 ─▶ Phase 2 ─▶ Phase 3
                └─▶ (parallel-safe: tests and docs)
```

## 5. Risk Register & Rollback
| Risk | Likelihood | Impact | Mitigation | Rollback |
|------|-----------|--------|-----------|----------|
| Refactor breaks persistent Discord views | H | H | Add compatibility registrations and interaction smoke tests; ship feature by feature | Restore monolith entry point and roll back one phase |
| SQLite async migration exposes locking regressions | M | H | WAL mode, bounded pool, transactions, and temp-DB integration tests | Disable async DB behind the facade and keep synchronous fallback temporarily |
| Scheduler misses a deadline or fires twice | M | H | Deadline recomputation, persisted sent flags, jitter, and property tests | Restore 20-second safety ticker as an opt-in fallback |
| Authorization change blocks legitimate roles | M | M | Preserve existing administrator/role behavior and add explicit config tests | Feature-gate stricter check and revert denied action paths |
| Config/token validation prevents startup | M | M | Clear startup diagnostics and `.env.example` | Run old launch command with legacy environment until corrected |

## 6. Acceptance Criteria (Definition of Done)
- [x] No module-global `bot`/`db`/`ACTIVE`; wiring only in `main.py`
- [x] Event loop never blocks on I/O; DB access is async
- [x] Idle CPU ≈ 0; no fixed-interval polling in steady state
- [x] All state-changing actions pass `permissions.authorize`; admin commands enforce server-side
- [x] Migrations are versioned and run empty → latest in tests
- [x] Core and shared coverage ≥ 90% (92% observed)
- [x] ruff + mypy + pytest are green
- [x] No secrets in repository; `.env.example` documents all config

## 7. Progress Log / Changelog
| Date | Phase/Step | Note |
|------|-----------|------|
| 2026-11-26 | Phase 0 | Activated plan; added tooling, config, logging, global command errors, guild allowlist, and server-side authorization checks |
| 2026-11-26 | Phase 0 | Verification: Python compile succeeded and 2 focused config tests passed |
| 2026-11-27 | Package migration | Moved the complete existing bot implementation into `thesnow/main.py`; retained `bot.py` as a compatibility launcher |
| 2026-11-27 | Modularization pass | Extracted database facade/migrations, config cache, shared constants/time/validation, and deadline scheduler; added feature package boundaries |
| 2026-11-27 | Optimization pass | Enabled SQLite WAL/NORMAL synchronous, indexed hot query columns, cached guild config, and removed the fixed 20-second polling loop |
| 2026-11-27 | Full fix & modular refactor | Converted DB to `aiosqlite` with `BEGIN IMMEDIATE` transactions, `PRAGMA user_version` migrations (`storage.last_ts TEXT -> INTEGER`), `AppContext` + 10 feature modules, native Modals + `FileUpload`, coalescing in-place panel edits, `DeadlineScheduler` (`asyncio.Event`, DST-safe UK slots, per-job fault isolation), central `permissions.py` + fail-closed reaction auth + `AlertAckView`, `tzdata`, and verified `ruff`, strict `mypy`, and 25 `pytest` tests (92% `core/`+`shared/` coverage). |
