# TheSnow Bot Bug Fixes, Async Modular Refactor & Performance Overhaul

* **Author:** naimur
* **Date:** 2026-11-27

## Overview

`thesnow` is a Discord family-management bot that runs interactive channel panels, logs, bonus tickets, reminders, events, and UK-time Cow Shed and Plantation alerts backed by SQLite. Today, `thesnow/main.py` (1,325 lines) still holds nearly all runtime logic with import-time database initialization, synchronous `sqlite3` calls inside `async` handlers, global state, empty `thesnow/features/*` and `thesnow/core/permissions.py` stubs, and several functional, data-integrity, and authorization bugs.

This brief defines a unified fix-and-modernization plan for bot operators and maintainers: eliminate runtime crashes and data-loss bugs, complete the transition to an asynchronous (`aiosqlite`) modular package layout, reduce Discord interaction latency via in-place panel edits and Discord modals (with attachment-backed screenshot proof where required), run an event-driven deadline scheduler with near-zero idle work, enforce explicit role-based authorization, and establish `ruff`, strict `mypy`, and `pytest` verification while preserving existing SQLite data, slash commands, and persistent button `custom_id`s.

## Analysis

### Current Baseline vs. Plan State

Direct inspection of the repository shows that `plan.md` marks Phase 0 complete and logs modularization and optimization passes, yet the refactor remains mostly on paper:

* `thesnow/main.py` triggers `load_dotenv()`, `configure_logging()`, `Database()`, and `migrate(db)` at module import time and leaves `settings` as `None` until `run()` executes.
* `thesnow/core/database.py` still runs synchronous `sqlite3` (`run`, `one`, `many`) with auto-commit per call, despite `aiosqlite>=0.20,<1` being listed in `pyproject.toml`.
* `thesnow/core/permissions.py` and all ten `thesnow/features/*/__init__.py` packages are one-line docstring stubs; `core/forms.py`, `core/embeds.py`, `core/errors.py`, and `core/context.py` do not exist.
* `pyproject.toml` sets `mypy` `strict = true` and `ruff` checks, while `thesnow/main.py` is untyped, existing files (`main.py`, `database.py`, `migrations.py`, `logging.py`) contain unused imports, and `pytest-asyncio` is missing from dev dependencies.
* `agents.md` cites `pydantic-settings`, `hypothesis`, `pip-audit`, and connection pooling, whereas `thesnow/config.py` uses standard-library `dataclasses` and `os.getenv`.

### Concrete Defects Verified in the Current Codebase

* **Broken choice prompts (`parse_answer` and `chat_form`):** `LOCATIONS` and `STORAGE_PLACES` in `thesnow/shared/constants.py` are `tuple`s, while `thesnow/main.py` checks `isinstance(kind, list)`, breaking numbered choice rendering and validation for Seeds and Shared Storage.
* **Inventory wipe on `/setup armory`:** Running `/setup` for Armory executes `reset_armory_zero`, deleting and zeroing all stored weapon, ammo, and vest counts. Every render of `e_armory` and every `armory_flow` open also executes 16 SQL writes (`DELETE` + 15 `INSERT OR IGNORE`).
* **Fail-open and emoji-blind reaction acknowledgments:** `on_raw_reaction_add` never verifies `str(payload.emoji) == "✅"`, and calls `guild.get_member` even though `Intents.members` is disabled. When a member is uncached (`None`), the role check is skipped and anyone can stop alerts.
* **Missing authorization on panels:** `SolarView`, `ArmoryView`, `StorageView`, and `FinanceView` have no server-side role checks; `SeedActionView` only checks roles when opening the ephemeral menu, not when clicking Add or Use; `ALLOWED_GUILD_IDS` is checked in `on_ready` but not on `on_guild_join`.
* **Legacy migration type mismatch:** `thesnow/core/migrations.py` creates `storage.last_ts` as `INTEGER` on new databases but alters existing tables with `last_ts TEXT`, causing `uk_str(row["last_ts"])` in `StorageView.find` to fail with `TypeError`.
* **Interaction response and Discord limit bugs:** `SolarView.repaired` calls `defer()` without sending a followup; `StorageView.find` sends an `ephemeral=True` followup after a non-ephemeral chat prompt (ignored by Discord); `View` and `Modal` errors have no `on_error` handler; `CloseView.close` lacks a double-click guard; `event_create` accepts negative `remind_before_min`; `/reminder remove`, `/diplomacy_done`, and `/event_delete` report success even when `rowcount == 0`; `clip()` bounds line counts instead of Discord's 1,024-character field, 4,096-character description, and 25-field limits; `num()` lacks a 64-bit signed integer upper bound.
* **Scheduler, query, and logging flaws:** `e_seeds` executes 12 SQL queries to render 6 rows; `ticker()` caps sleep at 120 seconds, checks `uk_now.minute == 0/30` (missing slots on delay or restart), treats UK `ZoneInfo` `timedelta(hours=1)` as elapsed time (colliding/skipping across DST shifts), aborts all guilds and reminders when one channel send raises an exception, ignores overdue items in `next_deadline`, and falls back to fixed schedules even when disabled; `configure_logging()` drops `extra={...}` fields.

### Core Contradictions & Inventive Resolutions

#### 1. Fast Modal UX vs. Choice Lists, Conditional Fields, and Durable Screenshot Proof
* **Contradiction:** Converting chat forms (`chat_form`) to `discord.ui.Modal` removes slow multi-message channel polling, but `discord.py >=2.4,<3` limits modals to at most 5 `TextInput` fields with no dropdowns, no dynamic conditional fields, and no reliable modal file uploads. Currently, `Armory` requires picking from 14 weapons, `Seeds` selects a location, `Storage` has conditional `plate` (`Vehicle` only) plus an image `proof`, and `Finance` (`pay`) requires an image `proof`. Furthermore, `parse_answer` currently accepts arbitrary `http(s)://` URLs (creating tracking-pixel/SSRF exposure) and `_delayed_delete(reply, 20)` deletes uploaded image messages after 20 seconds, breaking Discord CDN URLs stored in `storage.last_img` and audit logs.
* **Resolution (Pre-Modal Selector + Inverted Proof Relay):**
  * Use single-step Modals directly for simple text/number flows (`Balance`, `Solar`, `Finance` loan creation, `Bonus` ticket and log, `Storage` find).
  * Use a two-step ephemeral `discord.ui.Select` or button pre-picker followed immediately by `send_modal()` for branched or choice-heavy flows: weapon `Select` -> quantity/reason Modal for `Armory`; `Warehouse` vs. `Vehicle` selector -> Modal omitting `plate` on `Warehouse` for `Storage`; action + location selector -> Modal for `Seeds`.
  * For screenshot proof (`Storage` add/take, `Finance` loan payment), reject arbitrary external URLs (`S3`) and accept only validated Discord image attachments. After modal submission, prompt for the attachment (without committing DB state until proof arrives or is canceled), copy the file via `await att.to_file()`, upload it directly into the permanent `log_channel` embed, delete the transient prompt/upload immediately, and store `(log_channel_id, log_message_id)` so `Find Item` can retrieve a valid attachment URL.
* **Secondary Trade-offs:** Adds one ephemeral click before the modal on `Armory`, `Storage`, and `Seeds`; re-uploading proof images uses bot upload bandwidth and requires a configured `log_channel` (or private upload thread when panel channels deny `Send Messages` / `Attach Files`); ephemeral pre-selectors expire after 15 minutes.
* **Ideal Final Result:** Users pick choices without typing errors, submit validated inputs in one modal, and attach proof once, leaving clean channels, no arbitrary external URLs, and durable log-backed screenshots.

#### 2. In-Place Panel Edits vs. Channel Drift and Concurrent Overwrites
* **Contradiction:** `repost_panel` deletes and re-sends panel messages on every action (`GET` + `DELETE` + `POST`), while `refresh_schedule_panel` already uses `msg.edit` (though catching broad `HTTPException` risks duplicate panels on transient 429/5xx). Switching all panels to in-place edits cuts API work to one `PATCH`, yet concurrent updates can overwrite newer state with older snapshots, and any remaining channel messages push static panels upward out of sight.
* **Resolution (Coalescing Partial-Message Refresher + Ephemeral Error Isolation):** Route all panel updates through a unified `PanelRegistry` and per-`(guild_id, feature)` single-flight coalescing refresher that calls `channel.get_partial_message(msg_id).edit(...)`, re-sending and updating `{feature}_msg` only on `discord.NotFound`. Convert `tell()` notices to ephemeral responses so bot messages stop burying panels.
* **Secondary Trade-offs:** Requires clean lifecycle management for background refresh tasks and means in-place panels stay stationary in channels where users chat unless panel channels are read-only or an optional bury-threshold repost rule is configured.
* **Ideal Final Result:** Bursts of panel edits collapse into a single `PATCH` reflecting the latest committed state without message flicker or stale overwrites.

#### 3. Non-Blocking `aiosqlite` vs. Check-Then-Act Races, `SQLITE_BUSY`, and Legacy `family.db` Safety
* **Contradiction:** Moving from synchronous `sqlite3` to `await` calls with `aiosqlite` exposes check-then-act stock, balance, and loan checks to concurrent interleaving (negative balances/stock, overpaid loans, split-brain Armory vest/weapon writes). At the same time, SQLite allows only one writer even in WAL mode, so a multi-connection write pool as noted in `agents.md` triggers `SQLITE_BUSY` errors.
* **Resolution (Single Serialized Writer + Atomic Conditional SQL + `PRAGMA user_version`):**
  * Use one serialized `aiosqlite` writer connection guarded by an `asyncio.Lock` and explicit `BEGIN IMMEDIATE` transactions (optionally paired with read-only WAL connections for read queries), rather than a multi-writer pool.
  * Perform balance, seed, solar, armory, storage, and loan guards atomically inside `BEGIN IMMEDIATE` using relative SQL updates (`qty = qty - ? WHERE ... AND qty >= ?` and `paid = paid + ? WHERE ... AND total - paid >= ?`) and normalized case-insensitive item keys (`storage`).
  * Track schema version via `PRAGMA user_version` (or `schema_version`), detecting existing unversioned 11-table `family.db` files, repairing `storage.last_ts` (`TEXT -> INTEGER` cast/table rebuild), adding `ix_loans_active`, and backing up pre-migration files before upgrades.
* **Secondary Trade-offs:** Write transactions serialize one at a time (negligible at Discord guild command rates), and async `ConfigCache` updates must happen only after transaction commit so rollbacks never poison cached config.
* **Ideal Final Result:** Event-loop handlers never block on disk I/O, concurrent clicks cannot cause negative inventory or overdrafts, and existing `family.db` files migrate cleanly without data loss.

#### 4. Event-Driven Zero-Idle Scheduler vs. Missed Slots, DST Shifts, and Guild Fault Isolation
* **Contradiction:** Sleeping until the exact next persisted deadline minimizes idle CPU, yet newly added reminders/events/schedules would sit delayed without wakeup notifications; exact-minute checks (`uk_now.minute == 0/30`) drop slots when startup or Discord rate limits cross a minute boundary; UK DST transitions double or skip `01:00`/`01:30`; and one failing channel aborts all other guilds and jobs.
* **Resolution (Event-Signaled Deadline Runner + Windowed UTC/DST Slots + Job Isolation):**
  * Replace the 120-second `ticker()` cap with an `asyncio.Event` woken immediately on any reminder, event, schedule, or acknowledgment mutation, returning `None` (wait indefinitely) when no work is pending.
  * Treat `value <= now` as immediately due, compute Cow Shed / Plantation slots in UTC with DST `fold`-aware `slot_key`s (`YYYY-MM-DD-HH:MM+HHMM`) within a bounded catch-up window, and refresh schedule panels on `/plantation_stop`.
  * Isolate each reminder, event, and guild schedule in its own `try/except` with backoff or advancement on permanent `NotFound`/`Forbidden` errors.
* **Secondary Trade-offs:** Requires every schedule-mutating service path to signal the scheduler and needs an explicit catch-up grace window decision (how late after downtime an alert should still fire vs. skip).
* **Ideal Final Result:** Idle steady state performs zero polling work while active reminders, events, and UK schedule slots survive restarts, DST transitions, and single-channel permission errors.

#### 5. Default Server-Side Role Checks vs. Member Self-Service and Uncached Gateway Reactions
* **Contradiction:** Applying `mod_role`/`deputy_role` across all actions by default protects `Solar`, `Armory`, `Storage`, and `Finance`, yet breaks regular member workflows (`TicketView` bonus requests and ticket-owner `CloseView`), while `on_raw_reaction_add` has no cached `Member` roles when `Intents.members` is disabled.
* **Resolution (Declarative Action Policy Matrix + DB-First Reaction Auth or Button Ack):**
  * Replace scattered `allowed()` checks with a central default-deny action matrix in `thesnow/core/permissions.py`: `admin_only` (`/setup`, `/set_roles`, `/plantation_*`), `deputy_only` (`bonus:log`), `staff` (`mod_role`/`deputy_role` for balance mutations, seeds, solar, armory, storage mutations, finance, reminders, events, alert acks — pending confirmation if any inventory view stays open to members), `ticket_owner_or_staff` (`ticket:close`), and `guild_member` + cooldown/open-ticket cap (`ticket:new`). Re-verify authorization on final submission, not only when opening a view.
  * Filter `on_raw_reaction_add` by `str(payload.emoji) == "✅"` and active `ack=0` DB rows first, then resolve `payload.member or guild.get_member(...) or await guild.fetch_member(...)`, failing closed if missing/unauthorized—or pair/replace with a persistent `✅ Mark Done` button whose interaction payload includes `Member.roles` with zero REST lookups and ephemeral denial feedback.
* **Secondary Trade-offs:** Locking previously open panels (`Solar`, `Armory`, `Storage`, `Finance`) changes live workflow for non-mod members unless a `member_role` or open rule is chosen; `fetch_member` adds one REST call per uncached reaction on active alerts.
* **Ideal Final Result:** Every sensitive command, button, modal, and alert acknowledgment passes one auditable authorization gate with clear user-facing error messages.

## Goals vs. Non-Goals

* **In-Scope Goals:**
  * Fix all verified functional, data-integrity, Discord limit, concurrency, migration, logging, and authorization bugs in `thesnow`.
  * Complete the async (`aiosqlite`) refactor with `AppContext` composition in `thesnow/main.py`, zero import-time DB/env side effects, and clean boundaries across `thesnow/core/`, `thesnow/shared/`, and `thesnow/features/*`.
  * Eliminate N+1 queries and sequential delete-repost panel overhead; adopt in-place partial-message panel edits and Discord modals (+ ephemeral selectors / attachment-only log-backed proof where needed).
  * Replace the 120-second capped ticker with an event-driven deadline scheduler supporting mutation wakeups, DST-safe UK slots, and per-job error isolation.
  * Preserve existing SQLite table data, slash command names, and all 22 persistent `custom_id`s via versioned migrations.
  * Pass `ruff`, strict `mypy`, and `pytest` (including `pytest-asyncio` unit, legacy-DB migration, concurrency, scheduler DST, and mocked Discord interaction tests).
* **Out-of-Scope Non-Goals:**
  * Migrating from SQLite to PostgreSQL or adding multi-process sharding.
  * Changing slash command names, breaking existing persistent `custom_id`s, or adding unrelated gameplay features.
  * Introducing `pydantic-settings` (keep the existing standard-library dataclass configuration in `thesnow/config.py`) or external HTTP image proxies.
  * Adding an in-memory rendered-embed cache (in-place mutation-driven edits already rebuild embeds only when state changes).

## Alternatives Weighed

* **Patch bugs in-place inside `thesnow/main.py` with sync `sqlite3` (plus `asyncio.to_thread`) and `@tasks.loop(seconds=30)` (raised by Contrarian / YAGNI lens; not selected for default hypothesis):** Lower short-term churn and avoids threading `await` through embed builders or maintaining an event-driven scheduler wakeup graph, at the cost of leaving the half-refactored `features/*` stubs and `plan.md` / `pyproject.toml` (`aiosqlite`) goals incomplete.
* **Group into 3–4 domain modules (`economy`, `inventory`, `scheduling`, `db`) or use native `discord.ext.commands.Cog` extensions instead of 10 `thesnow/features/*` packages (raised by Contrarian / YAGNI lens; open to user preference):** Cuts boilerplate files on tiny 40–80 line features (`bonus_log`, `events`, `solar`, `seeds`) and uses `discord.py`'s built-in extension lifecycle instead of custom `AppContext`/`PanelRegistry` plumbing.
* **Replace screenshot-proof buttons (`Storage`, `Finance:pay`) with slash commands accepting `discord.Attachment` (raised by Contrarian / YAGNI lens; not selected):** Eliminates `wait_for("message")` and `Intents.message_content` completely, but changes user workflow away from clickable channel panels.
* **Replace `✅` alert reaction acknowledgments with a persistent `✅ Mark Done` button (raised by Contrarian, Comprehension, and Inventive Catalyst lenses; open recommendation):** Delivers authoritative `Member.roles` directly on interaction without `Intents.members` or `fetch_member` REST calls and gives unauthorized clickers immediate ephemeral feedback instead of silent failure.
* **Multi-connection `aiosqlite` writer pool (proposed in `agents.md` §2.1/§3.1; rejected on technical grounds):** Rejected because SQLite permits only one active writer even in WAL mode, so pooled writer connections cause `SQLITE_BUSY` contention without improving write concurrency.

## Key Decisions & Staging for Next Steps

* **Open Questions Requiring Alignment Before `/egm-draft`:**
  1. **Panel & Read-Lookup Access Policy:** Confirm which of `SolarView`, `ArmoryView`, `StorageView`, and `FinanceView` should be restricted to `mod_role`/`deputy_role` vs. open to all guild members, whether read-only lookups (`bal:check`, `bal:hist`, `sto:find`, `/reminder list`, `/event_list`) stay open to all members, and whether `BonusLogView` remains `deputy_role`-only.
  2. **Screenshot Upload Channel Constraint & Proof Policy:** Decide how proof uploads behave when panel channels block member messages (`Send Messages` / `Attach Files`)—such as temporary threads or an upload prompt—and confirm rejecting arbitrary external `http(s)` image URLs completely.
  3. **Refactor Granularity & Alert Ack UX:** Confirm whether to keep the 10-feature layout from `plan.md` (with `core/` + `features/*` built directly as async + modals) or consolidate small features, whether to add/replace `✅` reaction acks with a `✅ Mark Done` button, and what downtime catch-up window (e.g., 15 minutes) applies to missed Cow Shed / Plantation alerts.
* **Staged Architecture Path (Eliminating Double Rewrites):**
  1. **Stage 1 — Dev Tooling & Async Core Foundation:** Add `pytest-asyncio` to `pyproject.toml`; build async `aiosqlite` `Database` (serialized `BEGIN IMMEDIATE` transactions) + async `ConfigCache`, `PRAGMA user_version` migrations (`storage.last_ts TEXT -> INTEGER`), central `permissions.py` policy matrix, `BaseView`/`BaseModal` error handling, `DeadlineScheduler` + deduplicated `shared/time.py`, `PanelRegistry` single-flight partial-message editor, and character-budgeted `validation.py`.
  2. **Stage 2 — Feature Extraction (Async + Modals + Tests Directly):** Migrate `bonus`, `solar`, `balance`, `seeds`, `finance`, `armory`, `storage`, `schedule`, `reminders`, and `events` into `thesnow/features/` with clean `service.py` (transactional DTOs) / `embeds.py` (pure formatters) / `views.py` separation, removing `ensure_armory_seeded` from reads and `reset_armory_zero` from `/setup`.
  3. **Stage 3 — Composition Root & Verification:** Strip monolith logic/globals out of `thesnow/main.py` into `setup_hook` + `AppContext`, remove unused imports, and enforce `ruff`, strict `mypy`, and `pytest` coverage gates.
