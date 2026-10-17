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
unfunded cents. Habit estimates, scenarios, limits, and forecast orchestration
will be added incrementally. There is no API, database, menu ingestion,
frontend, NumPy, pandas, or forecasting dependency.

Run the tests with:

```bash
python -m pytest
```
