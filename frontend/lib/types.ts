export type Scenario = "frugal" | "expected" | "higher";
export type Account = "dining_dollars" | "triton_cash";

export type AuthStatus = {
  authenticated: boolean;
  consent_active: boolean;
  consent_version: string;
  consent_document_url: string;
};

export type HabitInput = {
  name: string;
  frequency: string;
  price_cents: number;
  eligible_accounts: Account[];
};

export type ForecastRequest = {
  start_date: string;
  end_date: string;
  habits: HabitInput[];
  dining_dollars_cents: number;
  triton_cash_cents: number;
  scenario?: Scenario;
};

export type Wallet = {
  dining_dollars_cents: number;
  triton_cash_cents: number;
};

export type DailyForecast = {
  date: string;
  expected_spending_cents: number;
  paid_dining_dollars_cents: number;
  paid_triton_cash_cents: number;
  unfunded_cents: number;
  remaining_balances: Wallet;
  funds_last: boolean;
};

export type ForecastResponse = {
  scenario: Scenario;
  multiplier: string;
  days: DailyForecast[];
  projected_balances: Wallet;
  total_unfunded_cents: number;
  funds_last: boolean;
  limits: {
    daily_wallet_runway_caps: Wallet;
    weekly_wallet_runway_caps: Record<string, Wallet>;
  };
};

export type PilotDay = {
  day: string;
  status: "checkin" | "zero_spending" | "unknown";
  checkin?: {
    dining_dollars_cents: number;
    triton_cash_cents: number;
  };
  zero_spending?: { confirmed_at: string };
};

export type PilotData = {
  start_date: string;
  end_date: string;
  days: PilotDay[];
  ledger_entries: Array<{
    occurred_on: string;
    account: Account;
    entry_type: "spending" | "deposit" | "refund";
    amount_cents: number;
    merchant_or_note: string | null;
  }>;
};

export type BalanceWarning = {
  account: Account;
  warning: boolean;
  current_balance_cents: number | null;
  threshold_cents: number;
  explanation: string;
};

export type BalanceWarnings = {
  dining_dollars: BalanceWarning;
  triton_cash: BalanceWarning;
  recorded_at: string | null;
};
