/** Tiny fetch wrapper. Always sends cookies so the session round-trips. */

const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API ${status}`);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      // ignore parse errors — error body is best-effort
    }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export type Me = {
  user_id: string;
  org_id: string;
  email: string;
  name: string;
  role: "org_admin" | "ops_lead" | "site_manager" | "viewer";
};

export type SiteOut = {
  id: string;
  name: string;
  timezone: string;
  operating_weekdays: number[];
  hours_per_day: number;
  rooms: number;
  active: boolean;
};

export type TrialOut = {
  id: string;
  name: string;
  status: "draft" | "active" | "archived";
  fpfv: string;
  lpfv: string;
  lplv: string;
  is_multi_arm: boolean;
  enrollment_target: number;
  screening_target: number;
  attrition_curve_id: string | null;
};

export type ArmOut = { id: string; trial_id: string; name: string };

export type SiteTrialOut = {
  id: string;
  site_id: string;
  trial_id: string;
  per_site_enrollment_target: number;
  per_site_screening_target: number;
  active: boolean;
};

export type EnrollmentWeekOut = {
  id: string;
  site_id: string;
  trial_id: string;
  arm_id: string;
  week_start: string; // ISO date
  proj_screened: number;
  proj_randomized: number;
  actual_screened: number | null;
  actual_randomized: number | null;
};

export type EnrollmentWeekHistoryOut = {
  id: string;
  enrollment_week_id: string;
  field: string;
  old_value: number | null;
  new_value: number | null;
  changed_by: string | null;
  changed_at: string;
};

export type TrialVarianceOut = {
  randomization: { sum_site: number; target: number; diff: number };
  screening: { sum_site: number; target: number; diff: number };
};

export type EnrollmentWeekIn = {
  week_start: string;
  proj_screened: number;
  proj_randomized: number;
  actual_screened: number | null;
  actual_randomized: number | null;
};

// --- Phase 4: forecast + metrics ---------------------------------------

export type ForecastCellOut = {
  site_id: string;
  week_start: string;
  visits_by_type: Record<string, number>;
  visits_by_trial: Record<string, number>;
  demand_hours: number;
  capacity_hours: number;
  utilization: number | null;
  revenue: number;
  week_range: { low_count: number; high_count: number };
};

export type DailyVisitsOut = {
  day: string;
  visits_by_type: Record<string, number>;
  demand_hours: number;
  capacity_hours: number;
  utilization: number | null;
};

export type MetricsRowOut = {
  screened: number;
  randomized: number;
  screen_fail_rate: number | null;
  screen_rate: number | null;
  enrollment_rate: number | null;
  pace_vs_plan: number | null;
  enrollment_health_randomized: number | null;
  enrollment_health_screened: number | null;
  wow_screened: number | null;
  wow_randomized: number | null;
};

export type TrialMetricsOut = {
  trial_id: string;
  trial_name: string;
  randomization_target: number;
  screening_target: number;
  metrics: MetricsRowOut;
};

export type ActiveTrialOut = { id: string; name: string };

export const api = {
  me: () => request<Me>("/auth/me"),
  login: (email: string, password: string, org_id: string) =>
    request<void>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, org_id }),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),

  listSites: () => request<SiteOut[]>("/sites"),
  listTrials: () => request<TrialOut[]>("/trials"),
  listArms: (trialId: string) => request<ArmOut[]>(`/trials/${trialId}/arms`),
  listAssignments: (trialId: string) =>
    request<SiteTrialOut[]>(`/trials/${trialId}/sites`),

  listEnrollmentWeeks: (
    siteTrialId: string,
    armId: string,
    from: string,
    to: string,
  ) =>
    request<EnrollmentWeekOut[]>(
      `/site-trials/${siteTrialId}/enrollment-weeks?arm_id=${armId}&from=${from}&to=${to}`,
    ),

  saveEnrollmentWeeks: (
    siteTrialId: string,
    armId: string,
    weeks: EnrollmentWeekIn[],
  ) =>
    request<EnrollmentWeekOut[]>(`/site-trials/${siteTrialId}/enrollment-weeks`, {
      method: "PUT",
      body: JSON.stringify({ arm_id: armId, weeks }),
    }),

  listEnrollmentHistory: (siteTrialId: string, armId: string) =>
    request<EnrollmentWeekHistoryOut[]>(
      `/site-trials/${siteTrialId}/enrollment-weeks/history?arm_id=${armId}`,
    ),

  getTrialVariance: (trialId: string) =>
    request<TrialVarianceOut>(`/trials/${trialId}/variance`),

  // Phase 4 — forecast + metrics
  networkForecast: (from?: string, to?: string) => {
    const qs = new URLSearchParams();
    if (from) qs.set("from", from);
    if (to) qs.set("to", to);
    return request<ForecastCellOut[]>(
      `/forecast/network${qs.toString() ? "?" + qs : ""}`,
    );
  },
  siteForecast: (siteId: string, from?: string, to?: string) => {
    const qs = new URLSearchParams();
    if (from) qs.set("from", from);
    if (to) qs.set("to", to);
    return request<ForecastCellOut[]>(
      `/sites/${siteId}/forecast${qs.toString() ? "?" + qs : ""}`,
    );
  },
  trialForecast: (trialId: string, from?: string, to?: string) => {
    const qs = new URLSearchParams();
    if (from) qs.set("from", from);
    if (to) qs.set("to", to);
    return request<ForecastCellOut[]>(
      `/trials/${trialId}/forecast${qs.toString() ? "?" + qs : ""}`,
    );
  },
  siteCalendar: (siteId: string, month: string) =>
    request<DailyVisitsOut[]>(
      `/sites/${siteId}/forecast/calendar?month=${month}`,
    ),
  trialMetrics: (
    trialId: string,
    window_start?: string,
    window_end?: string,
    site_id?: string,
  ) => {
    const qs = new URLSearchParams();
    if (window_start) qs.set("window_start", window_start);
    if (window_end) qs.set("window_end", window_end);
    if (site_id) qs.set("site_id", site_id);
    return request<TrialMetricsOut>(
      `/trials/${trialId}/metrics${qs.toString() ? "?" + qs : ""}`,
    );
  },
  siteMetrics: (siteId: string, window_start?: string, window_end?: string) => {
    const qs = new URLSearchParams();
    if (window_start) qs.set("window_start", window_start);
    if (window_end) qs.set("window_end", window_end);
    return request<TrialMetricsOut[]>(
      `/sites/${siteId}/metrics${qs.toString() ? "?" + qs : ""}`,
    );
  },
  listActiveTrials: () => request<ActiveTrialOut[]>("/active-trials"),
};
