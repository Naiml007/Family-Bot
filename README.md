# TheSnow Discord Bot

A family-management Discord bot for tracking shared balance, seeds, solar batteries, armory inventory, shared storage with screenshot proof, loans, bonus tickets/logs, UK-time Cow Shed and Plantation alerts, custom repeating reminders, diplomacy timers, and scheduled events.

---

## 1. Requirements & Installation

* **Python:** `3.11+` (tested on `3.12`)
* **Package Manager (recommended):** [`uv`](https://docs.astral.sh/uv/)
* **Dependencies:** Managed in [`pyproject.toml`](pyproject.toml) (`discord.py>=2.7`, `aiosqlite`, `python-dotenv`, `tzdata`)

Install dependencies into `.venv`:

```powershell
uv sync
```

To also install developer tools (`pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`):

```powershell
uv sync --extra dev
```

---

## 2. Configuration (`.env`) & `ALLOWED_GUILD_IDS`

Copy [`.env.example`](.env.example) to `.env` in the repository root and set your values:

```dotenv
DISCORD_TOKEN=replace-with-your-bot-token
GUILD_ID=
ALLOWED_GUILD_IDS=
DB_PATH=family.db
LOG_LEVEL=INFO
```

### Environment Variable Reference

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DISCORD_TOKEN` | Yes | — | Your Discord bot token from the Discord Developer Portal. Startup exits immediately with `ConfigError` if missing or blank. |
| `GUILD_ID` | No | Empty | Optional single server (guild) ID used **only** for fast slash-command syncing at startup (`copy_global_to` + `sync`). Leave blank to sync globally across all servers (global sync can take up to an hour to propagate in Discord). |
| `ALLOWED_GUILD_IDS` | No | Empty | Optional comma-separated **server allowlist** (see section below). |
| `DB_PATH` | No | `family.db` | SQLite database file path. Created automatically on bot startup if missing; existing databases migrate automatically with a timestamped `.bak-<unix_ts>` backup. |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `SCHEDULE_GRACE_SECONDS` | No | `900` | Catch-up window in seconds (default 15 minutes) for firing missed Cow Shed / Plantation alerts after bot downtime or restart. |

### What is `ALLOWED_GUILD_IDS`?

`ALLOWED_GUILD_IDS` restricts which Discord servers (guilds) the bot is allowed to operate in.

* **When empty (`ALLOWED_GUILD_IDS=`):** The bot will stay in and respond inside any Discord server where someone invites it.
* **When set (e.g. `ALLOWED_GUILD_IDS=123456789012345678` or `123456789012345678,987654321098765432`):**
  1. At startup (`on_ready`), the bot automatically leaves any Discord server whose ID is not in `ALLOWED_GUILD_IDS`.
  2. Whenever the bot is invited to a new server (`on_guild_join`), if that server ID is not listed in `ALLOWED_GUILD_IDS`, it immediately leaves.
  3. Commands, button/modal interactions, scheduled alerts, and reaction checks also refuse to execute for any unlisted server ID.
* **`ALLOWED_GUILD_IDS` vs. `GUILD_ID`:**
  * `GUILD_ID` only controls **where slash commands are synced quickly** during startup; it does **not** block other servers.
  * `ALLOWED_GUILD_IDS` is the **security allowlist** that stops unauthorized servers from using your bot if your invite link is leaked. If you set both, make sure `GUILD_ID` is also included inside `ALLOWED_GUILD_IDS`.

#### How to get a Discord Server (Guild) ID
1. In Discord, go to **User Settings → Advanced** and enable **Developer Mode**.
2. Right-click your server icon and click **Copy Server ID**.

---

## 3. Running the Bot

### Discord Developer Portal Setup
Before inviting the bot, configure it in the Discord Developer Portal:
1. Create a bot application and copy its token into `.env` as `DISCORD_TOKEN`.
2. **Privileged Gateway Intents:** None required (`Message Content Intent` and `Server Members Intent` can stay disabled; forms use native Discord modals and reaction verification fetches uncached members on demand).
3. **Bot Permissions (`OAuth2 → URL Generator`, scopes: `bot` + `applications.commands`):**
   * `View Channels`
   * `Send Messages`
   * `Embed Links`
   * `Attach Files`
   * `Read Message History`
   * `Add Reactions`
   * `Manage Channels` (required for creating/closing private Bonus Request tickets)
   * `Manage Messages` (required to delete acknowledged alert ping messages and old setup panels)

### Start Commands

Run via `uv`:

```powershell
uv run python bot.py
```

Or via the installed console script:

```powershell
uv run thesnow
```

### Initial Server Setup Order
Once the bot is online in your server, an **Administrator** should run:
1. `/set_roles moderator:@ModRole deputy:@DeputyRole` — sets the Discord roles permitted to manage family resources and alerts.
2. `/setup` — run once for each panel you want to enable, choosing the panel channel and (recommended) a log channel.
3. `/plantation_setup` — sets up the live Cow Shed and Plantation status panels and ping role (optional, if your family uses UK-time farm timers).

---

## 4. How Commands & Panels Work

### Role Hierarchy
* **Administrator:** Discord `Administrator` permission bypasses all role checks and is required for `/setup`, `/set_roles`, `/plantation_setup`, and `/plantation_stop`.
* **Deputy (`deputy_role`):** Allowed to log bonus payouts (`bonus:log`), perform all Staff actions, and close any bonus ticket.
* **Moderator (`mod_role`):** Allowed to perform all Staff actions (deposits, withdrawals, seeds, solar, armory, storage store/take, loans, reminders, diplomacy, events, and acknowledging farm alerts) and close any bonus ticket.
* **All Server Members:** Can check current balance (`Check Balance`), view recent balance history (`History`), search storage (`Find Item`), list reminders (`/reminder list`), list upcoming events (`/event_list`), open private bonus request tickets (`Create Bonus Request`), and close their own ticket (`Close Ticket`).

### Admin Commands

| Command | Who | Options & Behavior |
| --- | --- | --- |
| `/set_roles` | Admin | `moderator`, `deputy`. Saves role IDs per server for permission checks and ticket channel access. |
| `/setup` | Admin | `feature`, `panel_channel`, `[log_channel]`. Posts the interactive panel message and records channel/message IDs. Re-running `/setup` for Armory preserves existing stock (`ensure_armory_seeded`). |
| `/plantation_setup` | Admin | `cowshed_channel`, `plantation_channel`, `role`. Posts live UK-time countdown panels and enables automated reminders (`01:00, 04:00, 07:00, 10:00, 13:00, 16:00, 19:00, 22:00` UK for Cow Shed; every `__:30` UK for Plantation). Pings `role` every 5 minutes until acknowledged. |
| `/plantation_stop` | Admin | Disables Cow Shed and Plantation automated alerts, clears active alerts, and resets both status panels back to normal countdown display. |

### Reminders, Diplomacy & Events

| Command | Who | Options & Behavior |
| --- | --- | --- |
| `/reminder add` | Mod / Deputy | `chapter`, `role`, `channel`, `every_hours` (`0.1`–`720`), `[message]`, `[first_at]` (`HH:MM` UK 24h). Schedules a repeating reminder. |
| `/reminder list` | Members | Displays up to 25 active repeating reminders and their next UK run times. |
| `/reminder remove` | Mod / Deputy | `reminder_id`. Deletes the reminder by ID (errors clearly if ID is not found). |
| `/diplomacy_setup` | Mod / Deputy | `channel`, `role`. Starts a repeating 7-day Diplomacy reminder. |
| `/diplomacy_done` | Mod / Deputy | Restarts the 7-day Diplomacy timer from the current time. |
| `/event_create` | Mod / Deputy | `title`, `date` (`DD/MM/YYYY`), `time_uk` (`HH:MM` UK 24h), `role`, `channel`, `[remind_before_min]` (`0`–`10080`, default `30`), `[description]`. Posts an announcement and schedules pre-event and start pings. |
| `/event_list` | Members | Lists upcoming scheduled events in UK time. |
| `/event_delete` | Mod / Deputy | `event_id`. Deletes an event by ID. |

### Interactive Panels (Posted via `/setup`)

All panel updates edit the existing panel message in place (`PATCH`) instead of deleting and re-posting, and open native Discord popup Modals for inputs:

1. **Family Balance (`balance`):**
   * `Cow Shed`, `Plantation`, `Other Deposit`, `Withdraw` *(Mod / Deputy)*: Atomic ledger updates preventing withdrawals above available balance. `Withdraw` records Player ID, IGN, amount, and reason.
   * `Check Balance`, `History` *(Members)*: Ephemeral balance check and last 10 transactions.
2. **Seeds (`seeds`):**
   * Click any of the 6 seed buttons (`Mandarins`, `Pumpkins`, `Cabbage`, `Pineapples`, `Cannabis`, `Mushrooms`) → pick `Add Seeds` or `Use Seeds` → choose location (`Plantation` / `Cow Shed`) and quantity in the modal *(Mod / Deputy)*.
3. **Solar Plantation (`solar`):**
   * `Added`, `Used`, `Sold`, `Mark Repaired` *(Mod / Deputy)*: Tracks battery stock, daily counts, total revenue, and last repair timestamp.
4. **Armory (`armory`):**
   * `Add to Armory`, `Use / Take` *(Mod / Deputy)*: Pick weapon from dropdown, enter weapon, ammo, and vest quantities (plus reason when taking). Weapon, ammo, and vest stock update atomically in one transaction.
5. **Shared Storage (`storage`):**
   * `I Stored Items`, `I Took Items` *(Mod / Deputy)*: Pick `Warehouse` or `Vehicle`, enter item details (plus last 3 license-plate characters for vehicles) and attach an image screenshot inside the modal (`FileUpload`, max 8 MB). The screenshot is re-uploaded to the configured `log_channel` so lookup links do not expire.
   * `Find Item` *(Members)*: Search by exact or partial item name ephemerally, showing current stock, location, last user, timestamp, and stored screenshot.
6. **Finance / Loans (`finance`):**
   * `Loan Taken`, `Loan Given`, `Pay Loan` *(Mod / Deputy)*: Track loans owed by or to the family. `Pay Loan` matches `#ID` or name, prevents overpayment, and requires a screenshot proof attachment.
7. **Bonus Request Tickets (`bonus_ticket`):**
   * `Create Bonus Request` *(Members, 30s cooldown, max 1 open ticket per user)*: Opens a private ticket channel visible to the requester, `mod_role`, and `deputy_role`, with a `Close Ticket` button usable by the requester or Staff.
8. **Bonus Logs (`bonus_log`):**
   * `Log Bonus Payment` *(Deputy / Admin only)*: Records paid bonuses and totals.
9. **Cow Shed & Plantation Alert Acknowledgment:**
   * When an alert fires, Staff (`mod_role`, `deputy_role`, or `Administrator`) can either click **✅ Mark Done** on the ping message or react with `✅` to stop the 5-minute re-pings and record completion time on the timer panel.

---

## 5. Development & Verification

Run linting, strict type checking, and the automated test suite:

```powershell
uv run --no-sync ruff check .
uv run --no-sync mypy thesnow
uv run --no-sync pytest -v --cov=thesnow/core --cov=thesnow/shared --cov-report=term-missing
```
