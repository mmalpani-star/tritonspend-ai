# TritonSpend AI developer handoff

## 1. Current repository state

Worktree:

```text
/Users/madhavmalpani/.copilot/repos/copilot-worktrees/tritonspend-ai/mmalpani-star-didactic-lamp
```

Branch:

```text
mmalpani-star-m1-persistence-foundation
```

The branch is based on the existing forecast application history. The current work is intentionally uncommitted. Preserve all of the following changes; do not reset, clean, stash, overwrite, or discard them without explicit permission:

```text
 M README.md
 M backend/app/main.py
 M frontend/app/page.tsx
 M frontend/lib/api.ts
 M frontend/lib/types.ts
 M pyproject.toml
?? .gitignore
?? alembic.ini
?? alembic/
?? backend/app/auth_routes.py
?? backend/app/config.py
?? backend/app/db.py
?? backend/app/models.py
?? backend/app/pilot_routes.py
?? backend/app/pilot_schemas.py
?? backend/app/security.py
?? backend/scripts/
?? backend/tests/conftest.py
?? backend/tests/test_auth.py
?? backend/tests/test_persistence.py
?? backend/tests/test_pilot.py
?? frontend/components/auth-panel.tsx
?? frontend/components/data-collection-panel.tsx
```

The Desktop checkout is separate and must remain untouched:

```text
/Users/madhavmalpani/.copilot/repos/tritonspend-ai
```

It is currently on `main` with no tracked diff. Do not copy files between worktrees.

## 2. Completed product stages

### Stage 1: persistence foundation

- SQLAlchemy 2.x configuration, application-scoped engine, session factory, and request cleanup.
- Alembic migrations with explicit upgrade/downgrade operations.
- Production database configuration that requires PostgreSQL; local/test environments may explicitly use SQLite.
- UTC-aware timestamps and `America/Los_Angeles` calendar-date policy.
- Integer cents for all monetary values.
- Schema tables:
  - `participants`
  - `invite_tokens`
  - `consents` (legacy consent snapshot)
  - `balance_checkins`
  - `ledger_entries`
  - `zero_spending_confirmations`
  - `forecast_snapshots`

### Stage 2: identity, sessions, consent, and CSRF

- Single-use invitation redemption with cryptographically random raw tokens.
- Only HMAC hashes of invite, session, and CSRF secrets are stored.
- `participant_sessions` and append-only `consent_events` were added by later migrations.
- Sessions have a 30-day absolute lifetime and a 7-day idle timeout.
- Sessions are revocable; deleted participants cannot authenticate.
- Pilot state-changing cookie-authenticated routes require a synchronizer CSRF token in `X-CSRF-Token`.
- Production requires explicit HTTPS public origin, HTTPS CORS origins, configured strong secrets, and secure cookies.
- Consent version/document URL are configuration-driven. Final consent wording and privacy policy are not invented by the code.
- Invitation creation is operator-only through `backend/scripts/create_invite.py`; there is no public invite-generation endpoint.

### Stage 3: data collection

- Authenticated participant balance check-ins for Dining Dollars and Triton Cash.
- Positive ledger entries for `spending`, `deposit`, and `refund`.
- Explicit zero-spending confirmations.
- Missing days remain `unknown`; absence of data is never treated as zero.
- Participant-scoped history endpoint returns daily statuses and ledger entries.

### Stage 4: deterministic balance warnings

- Participant-specific Dining Dollars and Triton Cash thresholds.
- Thresholds use integer cents and nonnegative validation.
- The latest recorded balance is compared with `current <= threshold`.
- Missing balances return an explicit unknown/no-warning response.
- No duplicate balance storage was introduced.

### Stage 5: export and deletion

- Participant-scoped JSON export, versioned as `stage5.v1`.
- Export includes balance check-ins, ledger entries, zero-spending confirmations, thresholds, forecast snapshots, and consent history.
- Export excludes invitation token hashes, session hashes, CSRF hashes, and other participants' data.
- `DELETE /api/v1/pilot/account` requires authentication, CSRF, and exact confirmation:

```json
{"confirmation":"DELETE_MY_DATA"}
```

- Deletion removes participant-owned operational records transactionally, revokes sessions, clears session CSRF hashes, and removes invite associations.
- The opaque participant row is retained with `deleted_at`.
- Append-only `consent_events` are retained as the minimum consent audit history.
- Deletion is allowed after consent withdrawal and does not affect other participants.

## 3. Architecture and important files

```text
src/tritonspend/       deterministic forecasting and wallet domain
backend/app/main.py    FastAPI app, CORS, router registration, forecast route
backend/app/schemas.py forecast request/response DTOs
backend/app/mapping.py forecast API/domain translation
backend/app/models.py  SQLAlchemy persistence models
backend/app/db.py      engine, session factory, Base, request dependency
backend/app/config.py  environment and production-security validation
backend/app/security.py secret hashing, session and auth dependencies, CSRF
backend/app/auth_routes.py invite redemption, status, CSRF, consent, logout
backend/app/pilot_routes.py collection, warnings, export, deletion, history
backend/app/pilot_schemas.py data-collection and export DTOs
backend/scripts/create_invite.py trusted operator invitation utility
frontend/app/page.tsx  forecast page and auth/data-collection integration
frontend/components/auth-panel.tsx
frontend/components/data-collection-panel.tsx
frontend/lib/api.ts     forecast and authenticated pilot API helpers
frontend/lib/types.ts   frontend request/response types
alembic/versions/       explicit schema migrations
backend/tests/          API, auth, persistence, and pilot tests
tests/unit/              forecasting and wallet domain tests
```

The existing forecast contract remains:

```text
POST /api/v1/forecasts
```

It remains usable without pilot authentication and does not silently become a data-collection endpoint.

## 4. Current API behavior

Authentication and consent:

```text
POST /api/v1/auth/redeem
GET  /api/v1/auth/status
GET  /api/v1/auth/csrf
POST /api/v1/auth/consent
POST /api/v1/auth/consent/withdraw
POST /api/v1/auth/logout
```

Pilot collection and warnings:

```text
POST /api/v1/pilot/balance-checkins
POST /api/v1/pilot/ledger-entries
POST /api/v1/pilot/zero-spending-confirmations
GET  /api/v1/pilot/data?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
POST /api/v1/pilot/balance-thresholds
GET  /api/v1/pilot/balance-warnings
```

Export and deletion:

```text
GET    /api/v1/pilot/export
DELETE /api/v1/pilot/account
```

All participant-owned queries use the authenticated session's participant ID, not a client-supplied participant ID. Writes require CSRF and active consent except deletion, which remains available after withdrawal so a participant can remove data. Reads after withdrawal remain limited to that authenticated participant.

## 5. Local setup and configuration

The isolated worktree already contains a local `.venv`; use it rather than the Desktop environment. If setting up another equivalent environment, install the declared backend/test extras from the worktree:

```bash
cd /Users/madhavmalpani/.copilot/repos/copilot-worktrees/tritonspend-ai/mmalpani-star-didactic-lamp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[backend,backend-test]'
```

Frontend dependencies are managed by the committed lockfile:

```bash
cd /Users/madhavmalpani/.copilot/repos/copilot-worktrees/tritonspend-ai/mmalpani-star-didactic-lamp/frontend
npm ci
```

Never print or commit secret values. Required explicit environment names:

```text
TRITONSPEND_ENV=local|test|production
DATABASE_URL
TRITONSPEND_TIMEZONE=America/Los_Angeles
TRITONSPEND_CONSENT_VERSION
TRITONSPEND_CONSENT_DOCUMENT_URL
TRITONSPEND_CONSENT_DOCUMENT_HASH (optional; otherwise server-derived)
TRITONSPEND_SESSION_SECRET
TRITONSPEND_CSRF_SECRET
TRITONSPEND_CORS_ORIGINS
TRITONSPEND_PUBLIC_ORIGIN
NEXT_PUBLIC_API_BASE_URL
```

For local development, explicitly select local mode. SQLite is allowed only in local/test mode:

```bash
export TRITONSPEND_ENV=local
export DATABASE_URL=sqlite:///./tritonspend.db
export TRITONSPEND_TIMEZONE=America/Los_Angeles
export TRITONSPEND_CORS_ORIGINS=http://localhost:3000
export TRITONSPEND_PUBLIC_ORIGIN=http://localhost:3000
export TRITONSPEND_CONSENT_VERSION=local-v1
export TRITONSPEND_CONSENT_DOCUMENT_URL=https://example.test/consent/local-v1
export TRITONSPEND_SESSION_SECRET='generate-a-local-secret'
export TRITONSPEND_CSRF_SECRET='generate-a-different-local-secret'
```

Use different, locally generated secret values; do not reuse the placeholders above. For separate operator and server processes, they must share the same local session and CSRF secrets.

Run migrations only against the intended local/test database:

```bash
TRITONSPEND_ENV=local DATABASE_URL=sqlite:///./tritonspend.db alembic upgrade head
```

Create a pilot invitation only on a trusted operator machine. The command prints a one-time token to stdout; treat that terminal output as sensitive and never paste it into logs or source:

```bash
python3 backend/scripts/create_invite.py --hours 72
```

Start the backend from the repository root:

```bash
TRITONSPEND_ENV=local DATABASE_URL=sqlite:///./tritonspend.db \
TRITONSPEND_CORS_ORIGINS=http://localhost:3000 \
TRITONSPEND_PUBLIC_ORIGIN=http://localhost:3000 \
TRITONSPEND_CONSENT_VERSION=local-v1 \
TRITONSPEND_CONSENT_DOCUMENT_URL=https://example.test/consent/local-v1 \
TRITONSPEND_SESSION_SECRET='local-secret-one' \
TRITONSPEND_CSRF_SECRET='local-secret-two' \
.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

The example secret strings are placeholders for local instructions only; replace them with strong generated values. Start the frontend in a second terminal:

```bash
cd frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

Do not use these local settings for production. Production requires a PostgreSQL URL, strong distinct secrets, HTTPS `TRITONSPEND_PUBLIC_ORIGIN`, HTTPS `TRITONSPEND_CORS_ORIGINS`, secure cookies, and a valid HTTPS consent-document URL. Deployment ingress must also enforce TLS; that is not configured in this repository.

## 6. Verified checks

Verified in this worktree on 2026-10-19:

```bash
.venv/bin/python -m pytest -q
```

Result: **113 passed**.

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

Results: lint passed with no ESLint warnings/errors; typecheck passed; production build passed with no warnings.

The focused student journey was exercised using disposable SQLite/TestClient fixtures: operator invite creation, redemption, auth status, CSRF bootstrap, consent acceptance, balance check-in, spending entry, threshold warning at equality, participant-scoped history/export including a fixture forecast snapshot, logout, deletion confirmation, post-deletion access rejection, preservation of a second participant, and the unchanged forecast API. No real participant data or secrets were used.

Startup verification on 2026-10-19:

- The frontend development server started successfully on a disposable local port and served the application.
- The backend migration and Uvicorn startup succeeded against a disposable SQLite database after installing the declared backend extras with `python -m pip install -e '.[backend,backend-test]'`. The OpenAPI document exposed all expected auth, pilot, export/deletion, and forecast routes.
- Before that install, this existing isolated virtual environment lacked `uvicorn`, so `.venv/bin/python -m uvicorn ...` failed with `No module named uvicorn`. This was an environment dependency gap, not an application-code defect. A fresh environment must install the declared extras before startup.

## 7. Manual browser smoke-test checklist

Use only disposable local/test data and a one-time invite. Start the backend, run migrations, create an invite from a trusted terminal, and start the frontend using the commands above. Do not paste invite tokens or secret values into tickets, logs, or source.

1. Open the frontend and verify the unauthenticated state offers invite-token redemption.
2. Redeem the operator-created invite; verify the UI changes to the authenticated consent-required state.
3. Verify the configured consent document URL and version are displayed, then accept the consent. Confirm the data-collection panel becomes available.
4. Submit a Dining Dollars balance check-in and a Triton Cash balance check-in with valid dates and integer-cent-compatible amounts.
5. Submit a spending entry and verify the entry succeeds; also verify invalid dates, zero/negative amounts, and unsupported transaction types are rejected.
6. Configure thresholds for both accounts. Record balances above, equal to, and below thresholds and verify warnings appear only when `current balance <= threshold`; verify a missing balance is shown as unknown rather than zero.
7. Open history and confirm only the current participant's check-ins, ledger entries, and explicit zero-spending confirmations are shown. Confirm missing dates are not inferred as zero spending.
8. Use “Download my data” and inspect the JSON schema/version and participant-owned balance, ledger, zero-confirmation, threshold, forecast-snapshot, and consent-history sections. Confirm it contains no invite, session, CSRF, or other-participant secrets.
9. Sign out. Verify protected data requests no longer succeed until the participant redeems/authenticates again.
10. Sign in again with a disposable invite if needed, choose account deletion, verify the exact confirmation is required, and confirm successful deletion explains that re-login is required. Verify protected access is rejected afterward.
11. If using two disposable participants, verify deleting the first leaves the second participant's history/export available and unchanged.
12. Submit the existing forecast request and verify its response contract remains unchanged.

## 8. Known limitations and unverified behavior

- No live browser session was exercised. Frontend lint, typecheck, and build passed, and the backend journey was exercised with disposable TestClient fixtures.
- PostgreSQL runtime, PostgreSQL migrations, connection pooling, and PostgreSQL-specific transaction/locking behavior were not live-tested.
- Production TLS termination, HTTP-to-HTTPS redirect, HSTS, trusted proxy headers, and deployment ingress behavior are not configured or verified in this repository.
- SQLite was used for migration and journey verification; do not treat that as PostgreSQL certification.
- The forecast endpoint does not automatically create forecast snapshots. Snapshot export support exists for participant-scoped snapshots created by an approved future path or fixture.
- Consent wording and privacy policy must be finalized before recruitment or real-data collection.
- Invitation creation is a trusted local/operator workflow, not an admin web UI.
- No UCSD eAccounts import, menu ingestion, ML, notification service, or analytics dashboard is implemented.

## 9. Prioritized next steps

Required before real pilot deployment:

1. Select and document the hosted PostgreSQL deployment, backups, migrations, connection limits, and secret management.
2. Verify production TLS-only ingress, HTTPS redirect, HSTS, secure forwarded-header handling, and explicit CORS/public-origin settings.
3. Exercise the complete flow in a staging environment with a real browser and PostgreSQL test database.
4. Finalize consent wording, privacy policy, retention/deletion policy, and participant support procedure.
5. Review operator invitation handling, token delivery, audit logging, and incident response.

Optional future product work:

1. Persist an immutable forecast snapshot whenever a participant explicitly saves a forecast.
2. Add richer date-range history views and participant-facing correction workflows.
3. Add data-quality/reconciliation tools for balance check-ins, deposits, refunds, and unknown days.
4. Evaluate real student data only after consent, privacy, retention, and security processes are approved.
5. Add menu-aware planning and ML evaluation only after a sufficiently reliable dataset exists.

## 10. Future account-registration milestone (not implemented)

The current pilot intentionally uses invite-only access and does not collect passwords, email addresses, or SSO credentials. A future registration milestone may add:

- Email/password registration with email verification.
- Password reset and recovery.
- Google sign-in.
- Optional GitHub, Apple, and Microsoft sign-in.

This is **NOT IMPLEMENTED**. Any migration must preserve the existing invitation-based pilot path, participant isolation, consent-before-write safeguards, CSRF protection, secure sessions, export, and deletion semantics. Do not replace invite redemption or silently migrate pilot participants without an explicit data/identity migration plan.

## 11. Safe handoff procedure

Before any new task:

1. `cd` to this exact worktree and run `git status --short --branch`.
2. Read and preserve every existing modified and untracked path listed above.
3. Run the relevant tests before editing; use the isolated `.venv` and frontend dependencies.
4. Make the smallest change that satisfies the requested behavior.
5. Run focused tests first, then the relevant full suite and frontend checks.
6. Inspect `git diff`, `git diff --check`, and `git status` before reporting.
7. Never run `git reset`, `git clean`, `git checkout`, `git stash`, destructive migration commands, or broad deletion unless the user explicitly authorizes it.
8. Never copy files into the Desktop checkout, modify `main`, commit, push, or merge unless separately authorized.
9. Never expose credentials, invite tokens, session secrets, CSRF secrets, `.env` contents, or private participant data in output or documentation.

## 12. PostgreSQL integration-test safety update — 2026-10-23

### Current status
- `backend/tests/test_postgres_integration.py` has been hardened, but no PostgreSQL integration test has been executed.
- Static checks passed: AST parsing, pytest collection (5 tests collected), and `git diff --check`.
- PostgreSQL migrations are at `20261019_0003` (`head`).
- Existing CORS changes in `backend/app/main.py` and `backend/tests/test_api.py` must be preserved.

### Safety requirements
- Before execution, independently review the final diff for target validation, server-side database identity, Alembic-head and empty-table checks, and cleanup on setup failures.
- Ordinary integration tests require `TRITONSPEND_POSTGRES_INTEGRATION=1` and `TRITONSPEND_ENV=test`.
- The committed concurrency test additionally requires `TRITONSPEND_POSTGRES_CONCURRENCY=1`.
- Abrupt process termination may leave synthetic rows from the concurrency test.
- Do not connect to PostgreSQL or execute these tests until a read-only review explicitly approves them.





## 12. PostgreSQL integration-test safety update — 2026-10-23

### Current status
- `backend/tests/test_postgres_integration.py` has been hardened, but no PostgreSQL integration test has been executed.
- Static checks passed: AST parsing, pytest collection (5 tests collected), and `git diff --check`.
- PostgreSQL migrations are at `20261019_0003` (`head`).
- Preserve existing CORS changes in `backend/app/main.py` and `backend/tests/test_api.py`.

### Safety requirements
- Review the final diff before running any PostgreSQL integration tests.
- Verify target validation, server-side database identity, Alembic-head and empty-table checks, and cleanup after partial setup failures.
- Ordinary tests require `TRITONSPEND_POSTGRES_INTEGRATION=1` and `TRITONSPEND_ENV=test`.
- The concurrency test additionally requires `TRITONSPEND_POSTGRES_CONCURRENCY=1`.
- Abrupt process termination may leave synthetic rows from the concurrency test.
- Do not connect to PostgreSQL or execute these tests until a read-only review explicitly approves them.

### Next action
Conduct a read-only final review of `backend/tests/test_postgres_integration.py`. Preserve all existing work. Do not reset, clean, stash, discard, commit, push, or merge without explicit authorization.

## 13. Disposable PostgreSQL integration-test environment — 2026-10-26

### What was added
- `compose.postgres-test.yml`: one `postgres:16.4` service, published only on `127.0.0.1:5433`, user `tritonspend`, database `tritonspend_test`, data on tmpfs (destroyed by `down`), fixed Compose project name `tritonspend-postgres-test`. The password comes from `TRITONSPEND_TEST_PG_PASSWORD` at runtime and is never committed.
- `backend/tests/postgres/init/01-disposable-marker.sql`: on first initialization, sets the database comment to `tritonspend-disposable-test`.
- `backend/tests/test_postgres_integration.py`, before any write, now verifies in order: URL target, server-side `current_database()`/`current_user`, the exact disposable marker comment, that `alembic_version` exists, that it holds exactly `20261019_0003`, and that all ten application tables are empty. Connections use a 5 s connect timeout, 5 s `lock_timeout`, and 30 s `statement_timeout`. `_settings(url)` now uses the gated URL. The concurrency assertion now compares `sorted(statuses)` with `[200, 400]`.
- `backend/tests/test_postgres_safety_gates.py`: database-free tests for the URL gate and every pre-write refusal.

### Status
- Only database-free checks have been run. No container has been started, no image pulled, no PostgreSQL connection made, no migration run against PostgreSQL, and no PostgreSQL integration test executed.
- Running the steps below requires separate explicit approval: they start Docker, pull an image on first use, and write to the disposable database.

### Exact commands (run from this worktree, in one terminal)

```bash
cd /Users/madhavmalpani/.copilot/repos/copilot-worktrees/tritonspend-ai/mmalpani-star-didactic-lamp

# 0. Start Docker Desktop first. Generate a throwaway password for this shell
#    only; never print, paste, or commit it.
export TRITONSPEND_TEST_PG_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
export TRITONSPEND_ENV=test
export DATABASE_URL="postgresql+psycopg://tritonspend:${TRITONSPEND_TEST_PG_PASSWORD}@127.0.0.1:5433/tritonspend_test"

# 1. Start the disposable database (first run pulls postgres:16.4) and wait
#    for the healthcheck.
docker compose -f compose.postgres-test.yml up -d --wait

# 2. Confirm the marker (read-only); expected output: tritonspend-disposable-test
docker compose -f compose.postgres-test.yml exec -T postgres \
  psql -U tritonspend -d tritonspend_test -tAc \
  "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = current_database()"

# 3. Migrate the disposable database to head.
.venv/bin/python -m alembic upgrade head

# 4. Rollback-only integration tests (concurrency test skips).
TRITONSPEND_POSTGRES_INTEGRATION=1 \
  .venv/bin/python -m pytest backend/tests/test_postgres_integration.py -q -rs

# 5. Committed concurrency test, only after step 4 passes.
TRITONSPEND_POSTGRES_INTEGRATION=1 TRITONSPEND_POSTGRES_CONCURRENCY=1 \
  .venv/bin/python -m pytest backend/tests/test_postgres_integration.py -q -rs -k concurrency

# 6. Optional negative check: without the marker the tests must refuse
#    ("disposable-test marker"); then restore it.
docker compose -f compose.postgres-test.yml exec -T postgres \
  psql -U tritonspend -d tritonspend_test -c "COMMENT ON DATABASE tritonspend_test IS NULL"
TRITONSPEND_POSTGRES_INTEGRATION=1 \
  .venv/bin/python -m pytest backend/tests/test_postgres_integration.py -q -rs
docker compose -f compose.postgres-test.yml exec -T postgres \
  psql -U tritonspend -d tritonspend_test -c "COMMENT ON DATABASE tritonspend_test IS 'tritonspend-disposable-test'"

# 7. Tear down. tmpfs means all data, including any rows left by a crashed
#    test, is destroyed. Then clear the variables so later commands in this
#    shell cannot reach the test database.
docker compose -f compose.postgres-test.yml down --remove-orphans
unset TRITONSPEND_TEST_PG_PASSWORD DATABASE_URL TRITONSPEND_ENV
```

If a run is interrupted, recover with step 7 and start again from step 1; do not delete rows by hand. After the first approved pull, the image can additionally be pinned by digest (`docker image inspect postgres:16.4 --format '{{index .RepoDigests 0}}'`).

## 14. Persistent forecast history and spending trajectory — 2026-10-26

### Behavior
- `POST /api/v1/pilot/forecasts` (session + CSRF + active consent) accepts only `end_date`, `scenario`, and `habits`. Balances are never accepted from the client; they are reconciled on the server and the result is saved as a `ForecastSnapshot`. No migration or table was added.
- `GET /api/v1/pilot/forecasts?limit=` (newest first, 1–100, default 20), `GET /api/v1/pilot/forecasts/{id}`, and `GET /api/v1/pilot/forecasts/{id}/trajectory` are participant-scoped reads. Another participant's ID returns the same 404 as a missing ID.
- The anonymous `POST /api/v1/forecasts` is unchanged and saves nothing.

### Reconciliation policy (`backend/app/participant_forecast.py`)
- Reference date: today in `America/Los_Angeles` (`pilot_today_provider`).
- Baseline: the latest check-in with `effective_date <= today`. A check-in is an end-of-day balance; ledger entries dated on the check-in day are assumed to be included and produce a warning. Entries dated after it through today are applied per wallet: spending subtracts, deposits and refunds add. Wallets never substitute.
- Missing baseline → 422. A wallet that would reconcile below zero → 422 naming the wallet; never clamped. A baseline older than 14 days → saved with a stale-data warning.
- Projection starts tomorrow, because today's recorded entries are already in the reconciled balance. Range limit: 366 projected days, 1–50 habits.

### Snapshot contents (`request_json.schema_version = "participant-forecast.v1"`)
Reference date, projection dates, the participant's request, the baseline check-in, each applied ledger entry (id, date, account, type, amount; no notes), reconciled balances, the warning thresholds at creation time (`targets`), warnings, and the exact core request. `response_json` is the unchanged forecast response. `engine_version` is `tritonspend-core-0.1.0+participant-forecast.v1`; bump it when the core or the reconciliation policy changes output. Export and deletion already cover these rows.

### Trajectory
Per wallet and day from the reference date: recorded check-ins (actual, never interpolated), the stored projection, and an ideal even spend-down from the reconciled balance to the saved threshold (or to $0 when none was set). When the starting balance is already below the target, no ideal line is produced. Snapshots without the v1 schema return 409.

### Verification status
Database-free backend suite: 175 passed, 6 skipped (PostgreSQL). Frontend lint, typecheck, and production build pass. `test_postgres_persists_participant_forecast_snapshots` was added to the PostgreSQL module but has not been run; no PostgreSQL operation has been performed. The trajectory UI has not been checked in a browser.

## 15. Email and password accounts — 2026-10-29

- `POST /api/v1/auth/signup` (email, password, password_confirmation) creates a participant plus a `user_accounts` row and signs in; `POST /api/v1/auth/login` signs in; the existing `POST /api/v1/auth/logout` (CSRF) signs out. Both new routes use the existing Origin check, random HMAC-hashed session tokens, httpOnly SameSite=Lax cookies, and 30-day/7-day expiry. Consent is still required before any participant write.
- Any well-formed email is accepted (not only @ucsd.edu) and stored trimmed and lowercased, unique case-insensitively. Email is **not verified**: there is no email delivery. Passwords are 8–128 characters, must match the confirmation, must not equal the email, and are stored only as Argon2id hashes (`argon2-cffi`, added to the `backend` and `backend-test` extras). Wrong password and unknown email return the same 401 message; unknown emails still run a dummy hash to avoid a timing difference.
- Account deletion also deletes the `user_accounts` row, so the email can be registered again; the export includes the account email. `GET /api/v1/auth/status` returns `email` (null for invite participants).
- Invitation redemption still exists for operator-issued pilot invites but is no longer shown in the UI.
- Migration `20261029_0004_user_accounts` adds the table. The PostgreSQL integration test now expects `20261029_0004`, so run `alembic upgrade head` on the disposable database before step 4 of section 13.
- Not implemented: password reset, email verification, social login, login rate limiting or lockout.
- Outstanding, needs approval: the existing local `tritonspend.db` is still at `20261019_0003`; signup and login fail there until `TRITONSPEND_ENV=local DATABASE_URL=sqlite:///./tritonspend.db .venv/bin/python -m alembic upgrade head` is run.

## 16. Wallet balances replace manual ledger entry — 2026-10-30

Students no longer record transactions. They save both wallet balances with an as-of date, and saved forecasts start from the latest saved balances. No migration or table was added; wallet balances are stored as `balance_checkins` rows (append-only, so earlier saves remain as history).

### API
- New `GET /api/v1/pilot/wallet` (session, participant-scoped): `latest`, `history` (newest first, up to 20, `effective_date <= today`), `days_since_update`, `stale` (more than 14 days), `stale_after_days`, `thresholds`, and `warnings` (null until thresholds are set).
- Saving balances still uses `POST /api/v1/pilot/balance-checkins`; thresholds still use `POST /api/v1/pilot/balance-thresholds`. Both keep session + CSRF + active consent.
- The ledger, zero-spending, and `/data` endpoints, their tables, and existing rows are unchanged and still included in export and deletion. Only the UI for them was removed.

### Saved forecast policy (snapshot schema `participant-forecast.v2`, engine `tritonspend-core-0.1.0+participant-forecast.v2`)
- Starting balances are the latest saved wallet balances (latest `effective_date <= today`, then latest `observed_at`), used exactly as entered. Ledger entries are not applied.
- A saved balance is an end-of-day observation for its as-of date, so projection starts the day after the as-of date. When that date is before today, the days in between are projected from habits (the core receives the projection start as its reference date so those days are not skipped) and a note is stored in `warnings`. Balances older than 14 days also get a stale reminder.
- `end_date` must be after today; at most 366 projected days counted from the projection start, otherwise 422 asking the student to update balances. No saved balances → 422.
- `request_json` stores `created_on`, `reference_date` (the as-of date), dates, the request (scenario and habits), `balance_source`, `wallet_balances` (the saved row used), `starting_balances`, `targets` (thresholds at creation), `warnings`, and `core_request`. Snapshots are never modified later.
- v1 snapshots (ledger-reconciled, `reconciled_balances`) remain listed, readable, and chartable; `reconcile` is kept only to document that legacy policy.

### Trajectory
Unchanged shape. `actual` is renamed in the UI to "saved balance (observed)": only balances saved for that exact day, never interpolated. The UI states that a change between saved balances can include deposits, refunds, or transfers and is not purchase spending.

### Frontend
- Dashboard: wallet panel (first-time setup form, or balances + last updated + "Update balances").
- "My data" became "Wallet & Alerts" (`#wallet`; old `#my-data` links redirect): wallet balances, warning amounts, download/delete.
- Create Forecast shows the starting balances it will use, or a prompt to add them first. Each saved forecast shows its stored inputs (created, period, starting balances, scenario, habits).
- As-of date, end date, and quick-estimate start date have click-to-open "i" explanations (`components/info-label.tsx`).

### Verification status
Database-free backend suite: 214 passed, 6 skipped (PostgreSQL). `test_postgres_persists_participant_forecast_snapshots` was updated for v2 but has not been run. Frontend typecheck and lint pass. Not checked in a browser.

## 17. Spending Trajectory page, same-day forecast starts, Pacific timestamps — 2026-10-30

### Forecast start date
- New wallet saves go through `POST /api/v1/pilot/wallet` (session + CSRF + consent, future dates rejected) and are stored as `balance_checkins` rows with `source = "wallet"`. No schema change.
- A wallet save is accurate on its as-of date before that day's spending, so forecasts from it start ON the as-of date (snapshot schema `participant-forecast.v3`, engine `...+participant-forecast.v3`). Example: as-of 2026-10-30 → forecast starts 2026-10-30.
- Rows from the older `POST /balance-checkins` endpoint (`source = "manual"`, including balances saved through the UI before this change) remain end-of-day check-ins: forecasts from them still start the next day and are saved as v2. Re-saving balances on the wallet form switches a student to same-day starts.
- `end_date` may now be today (one-day forecast) but never before the forecast start. Existing snapshots are untouched.

### Trajectory (`GET /forecasts/{id}/trajectory`)
- Points cover exactly the forecast period: point 0 is the start of the first forecast day (`moment: "start"`, projected = stored starting balances); point k is the end of forecast day k (`moment: "end"`, projected = that day's stored `remaining_balances`).
- `actual` is a saved balance placed at the boundary it describes (wallet saves: start of their as-of day; older check-ins: end of their as-of day), with `actual_as_of`. Nothing is interpolated.
- `ideal` spends evenly from the stored starting balances to the stored `targets` (thresholds at creation, else $0), exactly hitting both endpoints. v1/v2 snapshots use the same layout.
- The charts moved from Create Forecast to the Spending Trajectory page (forecast selector, defaulting to the forecast just created or the newest).

### Timestamps
- Cause of "7:49 AM" instead of "12:49 AM": SQLite returns stored UTC timestamps without an offset, the API serialized them without one, and the browser parsed offset-less ISO strings as local time.
- Fix: every response timestamp in `pilot_schemas.py` is `UtcDateTime` (always serialized with `Z`); the export's participant timestamps too. Stored values are unchanged.
- Frontend: `frontend/lib/datetime.ts` is the only place dates/times are formatted. Timestamps are shown in `America/Los_Angeles` via `Intl` (DST automatic; offset-less input treated as UTC). Date-only values are formatted as calendar days without time-zone conversion.

### Tests
Backend database-free suite: 221 passed, 6 skipped (PostgreSQL). Frontend: `npm test` (Node's built-in runner, no new dependencies) runs `lib/*.test.mjs`, 10 tests, passing under `TZ` = America/Los_Angeles, Pacific/Kiritimati, Pacific/Pago_Pago, and UTC. Typecheck and lint pass. Not checked in a browser.

## 18. Forecast deletion and the personalized prediction model — 2026-10-30

### Deleting a saved forecast
`DELETE /api/v1/pilot/forecasts/{id}` (session + CSRF + active consent). Deletes only that snapshot; another participant's or a missing ID returns 404. Wallet history, thresholds, other forecasts, and the account are untouched. The UI asks first in a native `<dialog>` (`components/confirm-dialog.tsx`) naming the forecast's save time and period; on success the list updates, a deleted selection falls back to the newest remaining forecast, and Spending Trajectory forgets it.

### Personalized prediction (`backend/app/personal_model.py`, `GET /api/v1/pilot/prediction?forecast_id=`)
- Computed on every request from the participant's own `balance_checkins` only, so each new wallet save changes the next prediction. No ledger data, habits, other participants, external services, model table, or migration.
- Observations: saves dated on or before today (Pacific); latest save per as-of date (then per boundary); placed at the start of the day they describe; sorted.
- Per wallet: interval pace = (previous − new) / days. Increases are reported as replenishments and excluded. Pace = weighted median, weight = days × 0.5^(age/21). Slower/faster = weighted 25th/75th percentiles with ≥3 usable intervals, otherwise ±25% sensitivity (labelled). Unusual intervals (pace > median + 3·max(MAD, median/2)) are flagged but kept.
- Confidence (no percentages): none (0 saves), starting (1 save or no usable decrease), preliminary (≤2 intervals or <7 days), developing, established (≥5 intervals, ≥21 days, and 25th–75th spread ≤ the median pace).
- Horizon rule: from the latest saved balance's boundary to the end of the selected forecast's end date if that is on or after it, otherwise 30 days. Paths drop linearly by their pace, floored at $0.00, integer cents (ties away from zero). Ideal: even spend-down from the latest balance to the selected forecast's saved targets (no forecast selected: current warning amounts; none: $0). No ideal when the balance is already below the target.
- `original_plan` is the selected snapshot's stored output on its own boundaries; snapshots are never modified.

### Verification status
Backend database-free suite: 239 passed, 6 skipped. Frontend `npm test`: 9 passed (three runtime time zones); typecheck and lint pass. Not checked in a browser.

## 19. Rolling-origin backtesting of the personalized model — 2026-10-30

`backend/app/backtest.py`; developer diagnostic `GET /api/v1/pilot/prediction/backtest?include_pairs=` (session only, the caller's own `balance_checkins`, read-only, nothing stored, no UI).

- **Retrospective simulation only.** Predictions served by `/prediction` are not persisted, so `persisted_predictions_evaluated` is always 0. Reports describe what the *current* algorithm would have predicted, never historical production accuracy.
- **Availability and leakage (evaluator `rolling-origin.v2`).** A check-in exists from when it was persisted (`created_at`, server-set; `observed_at` can be client-supplied on the legacy route). Cutoffs are the ends of the Pacific days on which something was saved; at each, the model gets only the check-ins saved by then, through the production dedup/day-boundary rules and `build_prediction` (no forecast selected). A backdated balance or same-date correction saved later cannot influence an earlier cutoff. The origin is the latest boundary known at the cutoff (if several cutoffs share one, the last is used); its balance is the value known then. Targets are current-truth observations after the origin within 21 days; the runtime check confirms each was saved after the cutoff.
- **Horizons.** Scored on the actual later save date. Buckets: 1 day (1), 3 days (2–4), 7 days (5–10), 14 days (11–21). Later observations past 21 days are counted in `later_observations_beyond_max_horizon`, not scored.
- **Metrics.** Error = predicted − actual (positive = predicted more money left). MAE, median absolute error, mean signed error (cents and dollars), pair counts, elapsed days covered, model-closer / baseline-closer / tied counts. No MAPE. Per wallet, overall and per horizon bucket, each split into replenishment pairs (balance rose between origin and target) and the rest; replenishments are always in the overall figures. Also grouped by how many observations the model had (`by_history`).
- **Baseline.** Persistence (balance stays at the origin balance), scored on exactly the same pairs. Pairs where the model had no pace (one observation, or no decreases yet) are counted as `pairs_without_model_prediction` and excluded from both. Verdict: `about_the_same` if MAEs are within 5% (or 1 cent), else `better` / `worse`. No significance test.
- **Insufficient data.** Any group with fewer than 5 scored pairs reports counts only (`status: insufficient_data`, metrics `null`).
- **Versions.** Each pair records the predictor's own `model_version`; `evaluate(..., predictor=...)` runs a new algorithm on the same origins and pairs. `evaluator_version` is `rolling-origin.v1`.
- **Limits.** Cutoffs are day-granular (end of the Pacific save day). Balances backfilled all at once produce no cutoffs, by design. Pairs from overlapping origins are correlated. As of 2026-10-30 the local database has no participant with two observation dates, so there are 0 scored pairs.

Backend database-free suite: 252 passed, 6 skipped.

## 20. Food Nearby, stage 1: wallet-aware food discovery — 2026-10-30

Frontend only; no backend, schema, migration, external service or API key.

- **Catalog** `frontend/lib/food-venues-data.ts` (static, curated, checked 2026-10-30, not live): 68 venues = 16 HDH venues (10 restaurants, 6 markets from HDH Menus & Hours) + 39 on-campus and 13 off-campus food locations from the visible Triton Cash participating-locations list. Excluded: non-food listings (Imprints, Triton Outfitters, UCSD Bookstore, The Trove), GrubHub (a platform), and HTML-commented entries ("Pacific Beach", "The Pizza Taproom (La Jolla Village Square)", marked Coming Soon).
- **Coordinates** only from the official campus map's public ArcGIS layers (Dining_Halls, Markets, Coffee, Cafes_and_Restaurants; most features are marked "Draft" there): all 16 HDH + 31 Triton Cash venues. None for off-campus merchants, and none where the map conflicts or is ambiguous (Art of Espresso, BCB at Revelle Plaza and School of Medicine) or has no entry (Flavorfull, Su Pan Bakery, Sun Dry Market, Muir Woods Coffee House, Dora Ristorante). Name differences accepted by building: Lemongrass BBQ ↔ "Lemongrass Farm Fresh Plates", The Bella ↔ "Bella Vista Social Club & Caffe", Bistro ↔ "The Bistro at the Strand".
- **Hours**: HDH's published weekly hours for the 16 HDH venues (overnight closes handled); none verified for Triton Cash merchants.
- **Wallets** (`walletEligibility` in `frontend/lib/food-venues.ts`, derived from where a venue is listed): HDH → Dining Dollars and Triton Cash accepted; listed partners → Triton Cash accepted, Dining Dollars not accepted (DD FAQ: HDH only); anything else → not verified, never accepted.
- **Location**: browser geolocation only after "Use my current location"; kept in React state, never sent or stored. Denied/unavailable/timeout/unsupported states with retry and an official campus-landmark fallback (`frontend/lib/campus-landmarks.ts`, campus map POI layer). Haversine straight-line distance; travel modes are a later stage.
- **Budget**: newest saved forecast that hasn't ended → existing `/prediction?forecast_id=` → daily target = ideal line's slope ((latest − saved target) / horizon days). Otherwise "No daily target yet". Venue-level only; "Budget fit unavailable — menu prices not yet verified."
- **UI** `frontend/components/food-nearby-view.tsx`: search, location, three categories, Dining Dollars / Triton Cash / Open now chips, compact wallet line, cards with expandable "Why this works for you" and Details, source/freshness note.
- **Tests** `frontend/lib/food-venues.test.mjs` (9): eligibility, catalog integrity, Haversine, Pacific clock across DST, hours incl. past-midnight, filters/search/sort, reasons, daily target.
