export type Scenario = "frugal" | "expected" | "higher";
export type Account = "dining_dollars" | "triton_cash";

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
