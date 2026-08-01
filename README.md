# VTU Backend Starter (FastAPI + Celery + PostgreSQL)

This is a **working skeleton**, not a finished product — it implements the
core logic that's hardest to get right and most dangerous to get wrong:
atomic wallet accounting, provider failover, async processing, and
reconciliation. Everything else (auth, KYC upload, notifications, admin UI)
is more standard CRUD you can layer on top.

## What's implemented and why it's structured this way

| File | What it does |
|---|---|
| `app/services/wallet_service.py` | Atomic, race-condition-safe debit/credit using `SELECT ... FOR UPDATE` row locks + an append-only ledger. This is the single most important file in the codebase. |
| `app/services/topup_service.py` | Reserves funds, then tries providers in priority order. Timeouts are treated as "unknown", not "failed" — critical distinction, see comments in the file. |
| `app/integrations/base.py` + `vtpass_client.py` + `reloadly_client.py` | Common interface so failover logic never needs to know which provider it's calling. |
| `app/services/reconciliation_service.py` + `app/tasks/reconciliation_tasks.py` | Celery Beat job every 5 minutes that resolves any transaction stuck in `PROCESSING` by querying the provider directly. |
| `app/api/routes_webhook.py` | Signature-verified webhook receiver, idempotent against duplicate/replayed callbacks. |
| `tests/test_wallet_service.py` | Proves the ledger logic: debit reduces balance, overdrafts are rejected, duplicate references are rejected, reversals restore balance. |

## Local setup — step by step

1. **Clone and enter the project, create your env file:**
   ```bash
   cp .env.example .env
   # edit .env with real/sandbox credentials once you have them
   ```

2. **Start Postgres + Redis:**
   ```bash
   docker compose up -d db redis
   ```

3. **Create a virtualenv and install dependencies (for running Alembic/tests locally):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Initialize the database schema** (this starter doesn't include Alembic
   migration files yet — generate your first one):
   ```bash
   alembic init alembic
   # edit alembic/env.py to import Base from app.core.database and set target_metadata = Base.metadata
   alembic revision --autogenerate -m "initial schema"
   alembic upgrade head
   ```

5. **Seed at least two providers** so failover has something to fail over to:
   ```sql
   INSERT INTO providers (id, code, name, is_active, priority, config)
   VALUES
     (gen_random_uuid(), 'vtpass', 'VTpass', true, 1, '{}'),
     (gen_random_uuid(), 'reloadly', 'Reloadly', true, 2, '{}');
   ```

6. **Run everything:**
   ```bash
   docker compose up --build
   ```
   - API: http://localhost:8000/docs (FastAPI auto-generated Swagger UI)
   - Worker and beat run automatically as separate containers.

7. **Run the wallet logic tests** (uses a disposable Postgres test DB, not SQLite —
   row-locking behavior isn't faithfully testable on SQLite):
   ```bash
   createdb vtu_test_db  # via psql, or docker exec into the db container
   pytest tests/ -v
   ```

## What to build next (in order)

1. **Auth** — phone/OTP signup, JWT issuance, KYC tier gating on transaction limits.
2. **`product_provider_mapping` table** — the starter simplifies this; in reality
   each `Product` needs a different `upstream_code` per provider (VTpass's code
   for "MTN Airtime" isn't the same as Reloadly's operator ID for it).
3. **Admin endpoints** — manually retry/refund a transaction, toggle a provider
   `is_active` flag (this is your kill switch when a provider is down).
4. **Rate limiting** on `/topups` per user (prevents abuse and runaway retries).
5. **Structured audit logging** shipped to an external store — don't rely on
   container stdout logs for financial audit trails.

## Sandbox credentials to get first

- VTpass: register at vtpass.com, request sandbox API access from their dashboard.
- Reloadly: register at reloadly.com, sandbox credentials are issued instantly
  for the topups-sandbox environment (no approval wait, unlike production).

Test both sandboxes thoroughly — including forcing timeouts/errors — before
wiring in a second live provider for real failover coverage.
