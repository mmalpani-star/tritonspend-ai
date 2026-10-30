export type Scenario = "frugal" | "expected" | "higher";
export type Account = "dining_dollars" | "triton_cash";

export type AuthStatus = {
  authenticated: boolean;
  /** Null for participants who joined through a pilot invitation. */
  email: string | null;
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

/**
 * One saved set of wallet balances. source "wallet": accurate on its as-of date before
 * that day's spending (forecasts start that day); older check-ins are end-of-day balances.
 */
export type WalletBalances = Wallet & {
  id: string;
  /** Calendar date, YYYY-MM-DD. */
  effective_date: string;
  /** UTC timestamp of when it was saved. */
  observed_at: string;
  source: string;
};

export type WalletStatus = {
  latest: WalletBalances | null;
  /** Newest first. */
  history: WalletBalances[];
  days_since_update: number | null;
  stale: boolean;
  stale_after_days: number;
  thresholds: Wallet | null;
  warnings: BalanceWarnings | null;
};

/** Starting balances come server-side from the latest saved wallet balances. */
export type ParticipantForecastRequest = {
  end_date: string;
  scenario: Scenario;
  habits: HabitInput[];
};

export type ParticipantForecastSummary = {
  id: string;
  created_at: string;
  start_date: string;
  end_date: string;
  engine_version: string;
  scenario: Scenario | null;
  funds_last: boolean | null;
  total_unfunded_cents: number | null;
  starting_balances: Wallet | null;
  projected_balances: Wallet | null;
  warnings: string[];
};

export type ParticipantForecastDetail = {
  id: string;
  created_at: string;
  start_date: string;
  end_date: string;
  engine_version: string;
  /** v2 snapshots store starting_balances; legacy v1 snapshots stored reconciled_balances. */
  inputs: {
    schema_version?: string;
    starting_balances?: Wallet;
    reconciled_balances?: Wallet;
    warnings?: string[];
    reference_date?: string;
    request?: { end_date?: string; scenario?: Scenario; habits?: HabitInput[] };
  } & Record<string, unknown>;
  forecast: Partial<ForecastResponse> & Record<string, unknown>;
};

export type TrajectoryTarget = {
  account: Account;
  target_cents: number;
  basis: "threshold" | "zero";
  ideal_available: boolean;
  explanation: string;
};

export type TrajectoryPoint = {
  date: string;
  /** "start": start of the first forecast day (the starting balance); "end": end of `date`. */
  moment: "start" | "end";
  actual: Wallet | null;
  /** The as-of date of the saved balance shown as `actual`. */
  actual_as_of: string | null;
  projected: Wallet | null;
  ideal: { dining_dollars_cents: number | null; triton_cash_cents: number | null };
};

export type ForecastTrajectory = {
  forecast_id: string;
  schema_version: string | null;
  as_of: string;
  start_date: string;
  end_date: string;
  starting_balances: Wallet;
  targets: TrajectoryTarget[];
  points: TrajectoryPoint[];
};

export type OptionalWallet = { dining_dollars_cents: number | null; triton_cash_cents: number | null };

/** Point 0 is the start of the axis' first day; later points are the end of `date`. */
export type PredictionPoint = {
  date: string;
  moment: "start" | "end";
  actual: OptionalWallet;
  actual_as_of: string | null;
  predicted: OptionalWallet;
  lower: OptionalWallet;
  higher: OptionalWallet;
  ideal: OptionalWallet;
  original_plan: OptionalWallet;
};

export type Confidence = "none" | "starting" | "preliminary" | "developing" | "established";

export type BalanceChange = { from_boundary: string; to_boundary: string; increase_cents: number | null; daily_pace_cents: number | null };

export type AccountPrediction = {
  account: Account;
  latest_cents: number | null;
  confidence: Confidence;
  confidence_text: string;
  usable_interval_count: number;
  span_days: number;
  /** Net balance decrease per day, in cents. */
  daily_pace_cents: number | null;
  lower_pace_cents: number | null;
  higher_pace_cents: number | null;
  range_basis: "learned_range" | "sensitivity" | null;
  predicted_end_cents: number | null;
  lower_end_cents: number | null;
  higher_end_cents: number | null;
  runs_out_on: string | null;
  target_cents: number;
  target_basis: "forecast_threshold" | "current_threshold" | "zero";
  ideal_available: boolean;
  replenishments: BalanceChange[];
  unusual_changes: BalanceChange[];
};

export type Prediction = {
  model_version: string;
  today: string;
  observation_count: number;
  latest: { as_of: string; boundary: string; observed_at: string; balances: Wallet } | null;
  horizon: { start: string; end_date: string; rule: "selected_forecast_end" | "default"; days: number } | null;
  comparison: { id: string; created_at: string; start_date: string; end_date: string; scenario: Scenario | null } | null;
  accounts: AccountPrediction[];
  points: PredictionPoint[];
};
