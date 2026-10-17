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
eligible the allocator charges Dining Dollars first, then Triton Cash. It never
charges an ineligible account, never makes balances negative, and reports
unfunded cents. Deterministic habit estimates and forecasts use exact
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
particular meals. There is no API, database, menu ingestion, frontend, NumPy,
pandas, or machine-learning dependency.

Run the tests with:

```bash
python -m pytest
```
