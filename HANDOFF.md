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
