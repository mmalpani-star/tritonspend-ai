# TritonSpend AI

The initial implementation is a deterministic dining-budget domain. It keeps
Dining Dollars and Triton Cash as separate wallets and will eventually accept
an inclusive start date, inclusive end date, structured eating habits, and both
wallet balances.

Balances and prices are stored as integer cents. Expected spending uses
`fractions.Fraction` so fractional meal frequencies do not introduce
floating-point error. Core date logic receives an explicit `today`; it never
reads the system clock. A range beginning before `today` is projected from
`today`, while a range ending before `today` is rejected.

The foundation contains money, foundational models and validation, and
inclusive timeline rules. Wallet accounting is implemented independently:
expenses must explicitly list eligible accounts, and when both accounts are
eligible the allocator splits the expense equally (any odd cent goes to Triton
Cash). If one account cannot cover its share, the uncovered part is charged to
the other eligible account, up to that account's available balance. It never
charges an ineligible account, never makes balances negative, and reports as
unfunded only the cents that no eligible account can cover. Deterministic habit estimates and forecasts use exact
`Fraction` frequencies and integer-cent charges. Each habit's exact expected
cost is multiplied by the scenario multiplier, then converted to stored cents
using the existing nearest-cent, half-up policy before being allocated as a
separate expense. Placeholder scenarios are frugal (`4/5`), expected (`1`),
and higher (`6/5`); these are configurable illustrative multipliers, not
calibrated probabilities. Daily and weekly limits are wallet runway caps, not
habit-aware spending recommendations: each wallet's starting balance is
divided independently across projected days, and Monday-Sunday weekly caps
prorate partial projected weeks by projected day count. These caps do not
account for payment eligibility and do not guarantee that a wallet can pay for
particular meals. There is no menu ingestion, NumPy, pandas, or machine-learning
dependency.

## API input limits

The API enforces these limits (constants in `backend/app/schemas.py`) and
answers a request that breaks one with `422`, never `500`. They apply equally
to anonymous forecasts (`POST /api/v1/forecasts`) and saved forecasts
(`POST /api/v1/pilot/forecasts`), which share one frequency rule
(`frequency_error`). The forecast form checks the same limits for earlier,
habit-specific feedback (`frontend/lib/forecast-limits.ts`), but the backend
is authoritative. The forecasting core itself is limit-free.

| Input | Limit | Why |
| --- | --- | --- |
| Forecast period | At most 366 inclusive days | A full academic year or a leap year; bounds the work per request. Saved forecasts count from the first day covered by the saved wallet balances. |
| Habits | 1 to 50 per saved forecast; at most 50 per anonymous forecast | Far more than a realistic set of dining habits. |
| Frequency string | `n` or `n/d`, ASCII digits only, at most 9 characters | Rejects Unicode digits (`²`, `١`) and oversized numbers before any integer parsing. |
| Frequency denominator | 1 to 365 | `1/365` is once a year; zero is undefined. |
| Frequency value | 0 to 24 per day | Allows hourly purchases. Zero stays valid. |
| Habit price | $0 to $1,000 (`100_000` cents) | Well above any single campus food purchase. |
| Wallet balance | $0 to $100,000 (`10_000_000` cents) per wallet | Applies to forecast balances, saved wallet balances, older balance check-ins, and warning amounts. Well above any Dining Dollars or Triton Cash balance. |
| Older ledger entry amount | Up to $100,000 | Same bound as balances. |

Why these bounds matter:

- **Exact amounts in the browser.** The largest possible cumulative amount is
  about `100_000 * 24 * 6/5 * 366 * 50`, or 5.3e10 cents, far below
  JavaScript's `Number.MAX_SAFE_INTEGER` (about 9.0e15), so every cent value in
  a response is exact when the frontend parses it.
- **Database safety.** Stored cents columns are 32-bit integers (up to about
  $21.4 million); the $100,000 cap keeps every saved amount far inside them
  without a migration. Records saved before the cap remain readable.
- **No server errors from bad input.** Unicode digits, zero denominators,
  very long strings, and far-future dates used to be able to reach integer
  parsing or date arithmetic and fail with `500`; they are now rejected first.

## Persistence foundation

The M1 persistence schema is managed with SQLAlchemy and Alembic. It stores
opaque participant identifiers, invite and consent history, balance check-ins,
immutable ledger entries, zero-spending confirmations, and forecast snapshots.
Calendar dates use `America/Los_Angeles`; timestamps are UTC-aware. IDs are
portable strings (UUID-shaped values are suitable for PostgreSQL), JSON fields
use SQLAlchemy's portable JSON type, and enums are represented as strings so
the same migrations work with SQLite for local development and PostgreSQL for
hosted deployment.

Local and test environments may omit `DATABASE_URL` and use SQLite defaults,
but `TRITONSPEND_ENV` must always be explicitly set to `local`, `test`, or
`production`. For local authentication across separate app/operator
processes, explicitly set the same `TRITONSPEND_SESSION_SECRET` and
`TRITONSPEND_CSRF_SECRET` in both processes; generated local fallback secrets
are process-local test conveniences.
Hosted deployments must set a PostgreSQL `DATABASE_URL`; production rejects
missing or SQLite URLs and never falls back to ephemeral storage. Optional
environment variables are `TRITONSPEND_ENV` (`local`, `test`, or
`production`) and `TRITONSPEND_TIMEZONE` (currently fixed to
`America/Los_Angeles`).

Run the initial migration with:

```bash
TRITONSPEND_ENV=local DATABASE_URL=sqlite:///./tritonspend.db alembic upgrade head
```

For hosted deployment, replace the URL with the PostgreSQL connection string
and set `TRITONSPEND_ENV=production`.

Stage 2 adds an explicit migration for `consent_events` and
`participant_sessions`:

```bash
TRITONSPEND_ENV=local DATABASE_URL=sqlite:///./tritonspend.db alembic upgrade head
```

Production also requires non-empty `TRITONSPEND_CORS_ORIGINS` (a
comma-separated HTTPS allowlist), `TRITONSPEND_CONSENT_VERSION`,
`TRITONSPEND_CONSENT_DOCUMENT_URL`, optionally
`TRITONSPEND_CONSENT_DOCUMENT_HASH`, `TRITONSPEND_SESSION_SECRET`, and
`TRITONSPEND_CSRF_SECRET`. Session cookies are HttpOnly, SameSite=Lax, Secure
in production, and expire after 30 days or 7 days idle. Invite, session, and
CSRF values are only stored as hashes. If no document hash is configured, the
server pins consent to SHA-256 of the configured version and document URL;
client-supplied mismatched hashes are rejected. The operator-only invite utility is:

```bash
python3 backend/scripts/create_invite.py --hours 72
```

Stage 3 provides authenticated participant-scoped balance check-in, ledger
entry, and explicit zero-spending confirmation endpoints. Missing days remain
unknown; no zero spending is inferred. Stage 4 adds participant-configured
Dining Dollars and Triton Cash thresholds, with deterministic warnings when
the latest recorded balance is less than or equal to its threshold. Thresholds
are integer cents and are stored separately from the existing balance
check-ins.

Invitation redemption intentionally occurs before authentication, so the
authenticated CSRF header is unavailable. It therefore rejects a supplied
untrusted `Origin` while allowing direct/operator redemption without an
`Origin`; all authenticated state-changing routes still require the CSRF
header.

Session activity renewal uses a separate, narrow transaction that updates only
the matching session row. Request-scoped application work is not committed by
authentication reads; request failures roll back their request session.

Stage 5 participant data controls are:

```text
GET    /api/v1/pilot/export
DELETE /api/v1/pilot/account
```

The export is a documented `stage5.v1` JSON object containing only the
authenticated participant's balance check-ins, ledger entries, explicit
zero-spending confirmations, configured thresholds, and consent-event history.
It never includes invite-token, session, or CSRF hashes. The export response
also sets a JSON download filename.

Account deletion requires the authenticated session, the `X-CSRF-Token`
header, and the exact JSON body
`{"confirmation":"DELETE_MY_DATA"}`. It transactionally removes that
participant's check-ins, ledger entries, zero-spending confirmations,
thresholds, forecast snapshots, legacy consent row, and invite associations;
revokes all participant sessions and removes their CSRF hashes. The participant
row is retained with `deleted_at` and append-only `consent_events` are retained
as the minimum consent audit record. Other participants are not affected.
Deletion is not gated by active consent, so a participant may delete after
withdrawing consent. The current session is revoked and the UI instructs the
participant to use a new invitation if they need to sign in again.

Run the tests with:

```bash
python -m pytest
```
