# Grand RP Family Bot — Plan

Discord bot that runs a Grand RP family: timers, money, inventory, quests, events, logs.

---

## 1. Decisions (single recommended path)

| Area | Choice | Why |
|---|---|---|
| Language | Python 3.12+ | Your stack, fast to build |
| Package manager | `uv` | Lockfile, fast, one tool |
| Discord lib | `discord.py` 2.x (slash commands, Cogs, persistent Views) | Mature, modular via extensions |
| DB | PostgreSQL 16 | Real concurrency, row locking, needed for multi-instance |
| ORM / migrations | SQLAlchemy 2.0 async + Alembic | Typed models, safe schema changes |
| Scheduler | Own DB-backed scheduler (not in-memory) | Reminders survive restarts, safe across instances |
| Config | `pydantic-settings` (`.env`) + per-guild settings in DB | Typed, validated |
| Logging | `structlog` (JSON in prod, pretty in dev) | Searchable, per-interaction correlation id |
| Errors | Global handler + Discord error channel (+ Sentry optional) | Easy debugging |
| Tests | `pytest` + `pytest-asyncio` + testcontainers/Postgres | Services tested without Discord |
| Lint/types | `ruff` + `pyright` | Enforced in CI |
| Deploy | Docker Compose (bot + postgres), GitHub Actions CI | Reproducible |

### Cluster: honest answer
One family = one guild. Sharding is only required near 2,500 guilds. **Do not build a cluster now.**
Instead build **cluster-ready**: stateless processes, all state in Postgres, scheduler uses
`SELECT ... FOR UPDATE SKIP LOCKED` so two instances never fire the same reminder. Running a second
instance later is then a config change, not a rewrite. If you ever serve many families, switch to
`AutoShardedClient` / multi-cluster launcher (Phase 6).

---

## 2. Requirements

### Functional (your list → modules)

| Feature | Module | Summary |
|---|---|---|
| Time reminder (Nourish, Cow Shed) | `reminders` | Start/stop timers, ping role/user when due, repeat |
| Family balance | `finance` | Current balance from ledger |
| Finance management | `finance` | Deposit / withdraw / transfer, categories, history, monthly report |
| Seeds update (Plantation, Cow Shed) | `inventory` | Seed counts per container, add/use, low-stock alert |
| Armory logs | `inventory` | Container `armory`, who took/put what, log channel |
| Shared storage logs | `inventory` | Container `shared_storage`, same flow as armory |
| Family quest | `quests` | Define quest, track member contributions, complete, reward |
| Bonus request | `bonus` | Member requests → leaders approve/deny via buttons → optional ledger payout |
| Solar plantation | `solar` | Battery count, repair status/timer, repair reminder |
| Diplomacy reminder | `diplomacy` | Meetings/treaties/deadlines with other families, reminders |
| Events logs & reminder | `events` | Create event, RSVP buttons, T-24h / T-1h / T-10m reminders, post-event log |

### Non-functional
- **Reliability:** reminders must fire after a crash/restart (late is OK, lost is not).
- **Auditability:** every money / inventory / approval change is an append-only record with actor + time.
- **Debuggability:** every interaction has a correlation id in logs and in the error message shown to the user.
- **Extensibility:** adding a feature = adding one folder, no edits to core.
- **Permissions:** role-based (Leader / Admin / Member), configurable per command.
- **Timezone:** store UTC, display in guild-configured timezone.

### Constraints
- Solo dev, AI-agent assisted → strict layering and `AGENTS.md` rules matter more than cleverness.
- Game timers/cooldowns are **not hard-coded**; admins set durations via config.

---

## 3. Architecture

```
            Discord Gateway
                  │
        ┌─────────▼──────────┐
        │  bot/ (thin layer) │  Cogs, slash commands, Views, embeds, checks
        └─────────┬──────────┘
                  │ calls
        ┌─────────▼──────────┐
        │ services/ (logic)  │  Business rules. No discord imports. Unit-tested.
        └─────────┬──────────┘
                  │ uses
        ┌─────────▼──────────┐        ┌────────────────────┐
        │ db/ (repositories) │◄──────►│ PostgreSQL         │
        └─────────▲──────────┘        └────────────────────┘
                  │ polls due rows
        ┌─────────┴──────────┐
        │ scheduler/         │  Fires reminders, posts via a notifier interface
        └────────────────────┘
```

**Rules**
1. Cogs parse input and format output only. Logic lives in `services/`.
2. `services/` never imports `discord`. They return plain dataclasses.
3. Only `db/repositories` touch SQLAlchemy sessions.
4. Scheduler talks to Discord through a `Notifier` protocol (easy to fake in tests).
5. Each feature is a self-contained module with a standard layout (below).

### Repo layout

```
family-bot/
├── AGENTS.md
├── PLAN.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── migrations/
├── src/familybot/
│   ├── __main__.py              # entrypoint
│   ├── app.py                   # bot factory, extension loader
│   ├── core/
│   │   ├── config.py            # pydantic-settings
│   │   ├── logging.py           # structlog setup, correlation id
│   │   ├── errors.py            # AppError hierarchy (user-safe messages)
│   │   ├── permissions.py       # role checks, decorators
│   │   ├── time.py              # UTC helpers, guild tz, duration parsing
│   │   └── embeds.py            # shared embed styles
│   ├── db/
│   │   ├── base.py              # engine, session, Base
│   │   ├── models/              # one file per module
│   │   └── repositories/
│   ├── scheduler/
│   │   ├── runner.py            # poll loop, SKIP LOCKED claim
│   │   └── notifier.py          # Notifier protocol + Discord impl
│   ├── modules/
│   │   ├── reminders/{cog.py,service.py,views.py,schemas.py}
│   │   ├── finance/
│   │   ├── inventory/
│   │   ├── quests/
│   │   ├── bonus/
│   │   ├── solar/
│   │   ├── diplomacy/
│   │   ├── events/
│   │   └── admin/               # status, reload, sync, config, debug
│   └── observability/
│       ├── health.py            # /healthz endpoint
│       └── audit.py             # audit log writer
└── tests/
    ├── unit/                    # services, no DB/Discord
    ├── integration/             # services + real Postgres
    └── conftest.py
```

### Module template (every feature follows this)
```
modules/<name>/
  cog.py        # slash commands only, thin
  service.py    # business logic
  views.py      # buttons/modals/selects (persistent, custom_id prefixed "<name>:")
  schemas.py    # dataclasses / pydantic DTOs
```
Plus: `db/models/<name>.py`, `db/repositories/<name>.py`, `tests/.../test_<name>.py`, one Alembic migration.

Extensions auto-load from `modules/*/cog.py`; a module can be disabled per guild via config
(`/admin module disable solar`).

---

## 4. Data model (core tables)

| Table | Key columns | Notes |
|---|---|---|
| `guild_settings` | guild_id, timezone, log_channel_id, error_channel_id, role map (json), enabled_modules | One row per guild |
| `members` | id, guild_id, discord_id, display_name, in_game_name | Links Discord ↔ in-game name |
| `reminders` | id, guild_id, kind, key, due_at, interval_seconds, target (role/user), channel_id, status, locked_at, attempts | Scheduler table. `kind`: nourish, cow_shed, diplomacy, event_*, solar_repair |
| `timers` | id, guild_id, kind, started_by, started_at, duration_seconds | Nourish / Cow Shed runtime state |
| `ledger_entries` | id, guild_id, amount (int), type, category, member_id, note, ref_id, created_at | **Append-only.** Balance = SUM(amount) |
| `inventory_items` | id, guild_id, name, category | seed, weapon, ammo, etc. |
| `inventory_moves` | id, guild_id, container, item_id, delta, member_id, note, created_at | **Append-only.** Container: plantation, cow_shed, armory, shared_storage |
| `quests` | id, guild_id, title, description, target, reward, status, deadline | |
| `quest_contributions` | id, quest_id, member_id, amount, created_at | |
| `bonus_requests` | id, guild_id, member_id, reason, amount, status, decided_by, decided_at, message_id | Approval via buttons |
| `solar_state` | guild_id, battery_count, needs_repair, repair_due_at, updated_by | Plus `solar_logs` history |
| `diplomacy_entries` | id, guild_id, family_name, type, title, due_at, notes | Creates a reminder row |
| `events` | id, guild_id, title, description, starts_at, channel_id, message_id, status | |
| `event_rsvps` | event_id, member_id, status | yes / maybe / no |
| `audit_log` | id, guild_id, actor_id, action, entity, entity_id, payload (json), correlation_id, created_at | Every mutation writes here |

Key design choices
- **Ledger + moves are append-only** → balance and stock are derived, nothing silently edited; corrections are new reversing entries.
- **Armory, shared storage, plantation, cow shed = one inventory engine** with a `container` column. Four features, one codebase.
- **Finance and balance = one ledger.** `/balance` is just a read.
- **Scheduler is generic.** Every "reminder" feature just inserts a row.

---

## 5. Commands (slash, grouped)

| Group | Commands |
|---|---|
| `/reminder` | `nourish start`, `cowshed start`, `list`, `cancel`, `config` |
| `/balance` | `show` |
| `/finance` | `deposit`, `withdraw`, `transfer`, `history`, `report`, `categories` |
| `/seeds` | `add`, `use`, `stock`, `update` (container: plantation / cow shed) |
| `/armory` | `put`, `take`, `stock`, `log` |
| `/storage` | `put`, `take`, `stock`, `log` |
| `/quest` | `create`, `list`, `contribute`, `progress`, `complete`, `cancel` |
| `/bonus` | `request`, `pending`, `history` (approve/deny = buttons for leaders) |
| `/solar` | `status`, `batteries set`, `repair start`, `repair done` |
| `/diplomacy` | `add`, `list`, `remind`, `done` |
| `/event` | `create`, `list`, `cancel`, `log` (RSVP = buttons) |
| `/admin` | `status`, `config`, `module enable/disable`, `reload`, `sync`, `debug`, `logs` |

Conventions: ephemeral replies for personal output, public embeds + log channel post for anything
that changes shared state, confirm buttons for destructive actions, autocomplete for item names.

---

## 6. Reliability & debugging

**Scheduler flow**
1. Loop every ~5s: claim due rows (`status='pending' AND due_at <= now()`) with `FOR UPDATE SKIP LOCKED`.
2. Mark `locked`, send through `Notifier`.
3. Success → `done` (or reschedule if `interval_seconds`). Failure → `attempts += 1`, exponential backoff, after N attempts → `failed` + error channel alert.
4. On startup, rows stuck in `locked` past a timeout return to `pending`.

**Debug toolkit**
- Correlation id per interaction → in every log line and in the user-facing error ("Error ref: `a1b2c3`").
- `AppError` subclasses carry a safe user message; unknown exceptions show a generic message and post the full trace to the error channel.
- `/admin status`: uptime, latency, DB ping, pending/failed reminders, loaded modules, version/commit.
- `/admin debug <ref>`: look up logs/audit by correlation id.
- `/healthz` HTTP endpoint for Docker healthcheck / uptime monitor.
- Dev: `jishaku` loaded only when `ENV=dev`.

---

## 7. Roadmap

| Phase | Scope | Done when |
|---|---|---|
| 0. Foundation | Repo, uv, config, logging, DB + Alembic, extension loader, error handler, `/admin status`, Docker, CI | Bot boots in Docker, CI green, `/admin status` works |
| 1. Scheduler + Reminders | Scheduler, Notifier, `reminders` module (Nourish, Cow Shed) | Restart mid-timer → reminder still fires exactly once |
| 2. Ledger | `finance` + `/balance`, audit log | Balance equals sum of entries, history paginated, every write audited |
| 3. Inventory | Seeds (plantation, cow shed), armory, shared storage, logs | Stock never negative, every move logged to channel |
| 4. Solar + Diplomacy | Both modules on top of scheduler | Repair and diplomacy reminders fire |
| 5. Quests + Bonus + Events | Buttons/modals, RSVP, approvals → ledger | Bonus approval creates ledger entry once (idempotent) |
| 6. Hardening | Backups, rate-limit handling, load test with 2 instances, metrics, docs | Two instances run with zero duplicate reminders |
| 7. (Only if needed) | Sharding / multi-guild / web dashboard | — |

Build order rationale: scheduler and ledger/inventory are the shared engines; everything else is thin on top.

---

## 8. Trade-offs & what to revisit

| Decision | Trade-off | Revisit when |
|---|---|---|
| Postgres over SQLite | Slightly more ops, but needed for locking and multi-instance | Never for this scale; SQLite only for throwaway dev |
| Own scheduler over APScheduler | ~150 lines to maintain, but restart-safe and cluster-safe | If you need cron-like complexity |
| Cluster-ready, not clustered | No Redis/queue overhead now | More than one guild, or >1 instance needed |
| Append-only ledger | More rows, simple reversal logic | Table >10M rows (add snapshots) |
| One inventory engine | Slight abstraction cost | If armory needs very different rules (e.g. per-weapon serials) |
| Slash commands only | No prefix commands | Never |
| Grand RP timers configurable | Admin must set durations once | If you want built-in defaults per game update |

**Assumptions to confirm during Phase 0** (put into `guild_settings`, not code): reminder durations for
Nourish/Cow Shed, battery max and repair interval, role names for Leader/Admin/Member, log channel IDs,
guild timezone.

---

## 9. Security & ops checklist
- Token and DB URL only in `.env` / secrets; `.env` in `.gitignore`.
- Minimal gateway intents (no message content, no presences).
- `allowed_mentions` restricted by default; mass pings only from the scheduler for configured roles.
- Permission checks in the service layer for money/approval actions (not only in the cog).
- Nightly `pg_dump` to off-box storage; test a restore once.
- Pin dependencies via `uv.lock`; Dependabot for updates.
