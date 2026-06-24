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

// --- Phase 5: documents + SoA parse jobs ----------------------------------

export type ParsedVisitOut = {
  name: string;
  visit_type: "screening" | "randomization" | "follow_up" | "other";
  target_day_offset: number;
  window_days: number;
  confidence: number;
  flagged_reason: string | null;
};

export type SoaParseJobOut = {
  id: string;
  document_id: string;
  trial_id: string | null;
  status: "queued" | "running" | "succeeded" | "failed" | "applied" | "discarded";
  model_id: string | null;
  prompt_version: string | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type SoaParseJobDetailOut = SoaParseJobOut & {
  parsed_visits: ParsedVisitOut[] | null;
};

export type TrialIn = {
  name: string;
  sponsor?: string | null;
  fpfv: string;
  lpfv: string;
  lplv: string;
  is_multi_arm?: boolean;
  enrollment_target: number;
  screening_target: number;
};

export type VisitIn = {
  name: string;
  visit_type: "screening" | "randomization" | "follow_up" | "other";
  target_day_offset: number;
  window_days?: number;
  duration_hours_override?: number | null;
  price?: number | null;
  sort_order?: number;
};

export type SiteTrialIn = {
  site_id: string;
  per_site_enrollment_target: number;
  per_site_screening_target: number;
};

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
  listTrialsAtSite: (siteId: string) =>
    request<
      Array<
        SiteTrialOut & {
          trial_name: string;
          trial_status: "draft" | "active" | "closed";
        }
      >
    >(`/sites/${siteId}/trials`),

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

  // Phase 5 — trial setup wizard
  createTrial: (payload: TrialIn) =>
    request<TrialOut>("/trials", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  patchTrial: (trialId: string, payload: Partial<TrialIn>) =>
    request<TrialOut>(`/trials/${trialId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  activateTrial: (trialId: string) =>
    request<TrialOut>(`/trials/${trialId}/activate`, { method: "POST" }),
  listVisits: (armId: string) =>
    request<
      Array<{
        id: string;
        arm_id: string;
        name: string;
        visit_type: string;
        target_day_offset: number;
        window_days: number;
        price: number | null;
        sort_order: number;
      }>
    >(`/arms/${armId}/visits`),
  createVisit: (armId: string, payload: VisitIn) =>
    request<{ id: string; name: string; visit_type: string }>(
      `/arms/${armId}/visits`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  patchVisit: (armId: string, visitId: string, payload: Partial<VisitIn>) =>
    request<{ id: string; name: string }>(
      `/arms/${armId}/visits/${visitId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  deleteVisit: (armId: string, visitId: string) =>
    request<void>(`/arms/${armId}/visits/${visitId}`, { method: "DELETE" }),
  assignSiteToTrial: (trialId: string, payload: SiteTrialIn) =>
    request<SiteTrialOut>(`/trials/${trialId}/sites`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listAttritionCurves: () =>
    request<
      Array<{ id: string; name: string; total_dropout_pct: number; is_preset: boolean }>
    >("/attrition-curves"),

  // Phase 5 — documents + SoA parse jobs
  uploadDocument: async (trialId: string, file: File): Promise<SoaParseJobOut> => {
    const fd = new FormData();
    fd.append("file", file);
    // Don't set Content-Type — browser must build the multipart boundary.
    const res = await fetch(`/api/trials/${trialId}/documents`, {
      method: "POST",
      credentials: "include",
      body: fd,
    });
    if (!res.ok) {
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        // best effort
      }
      throw new ApiError(res.status, body);
    }
    return (await res.json()) as SoaParseJobOut;
  },
  getParseJob: (jobId: string) =>
    request<SoaParseJobOut>(`/parse-jobs/${jobId}`),
  getParsedVisits: (jobId: string) =>
    request<SoaParseJobDetailOut>(`/parse-jobs/${jobId}/parsed-visits`),
  applyParseJob: (
    jobId: string,
    payload: { arm_id: string; visits: ParsedVisitOut[] },
  ) =>
    request<
      Array<{
        id: string;
        name: string;
        visit_type: string;
        target_day_offset: number;
        window_days: number;
      }>
    >(`/parse-jobs/${jobId}/apply`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  discardParseJob: (jobId: string) =>
    request<void>(`/parse-jobs/${jobId}/discard`, { method: "POST" }),

  // Phase 6 — admin settings (users, exports)
  listUsers: () =>
    request<
      Array<{
        id: string;
        email: string;
        name: string;
        role: Me["role"];
        active: boolean;
      }>
    >("/users"),
  createUser: (payload: {
    email: string;
    name: string;
    password: string;
    role: Me["role"];
  }) =>
    request<{ id: string; email: string; name: string; role: Me["role"]; active: boolean }>(
      "/users",
      { method: "POST", body: JSON.stringify(payload) },
    ),
  patchUser: (
    userId: string,
    payload: { name?: string; role?: Me["role"]; active?: boolean },
  ) =>
    request<{ id: string; email: string; name: string; role: Me["role"]; active: boolean }>(
      `/users/${userId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  listSiteUsers: (siteId: string) =>
    request<
      Array<{
        assignment_id: string;
        user_id: string;
        email: string;
        name: string;
        role: Me["role"];
      }>
    >(`/sites/${siteId}/users`),
  assignUserToSite: (siteId: string, userId: string) =>
    request<{ assignment_id: string; user_id: string }>(`/sites/${siteId}/users`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),
  unassignUserFromSite: (siteId: string, userId: string) =>
    request<void>(`/sites/${siteId}/users/${userId}`, { method: "DELETE" }),

  // Phase 6 — OrgSettings (already in backend; thin client wrapper)
  getOrgSettings: () =>
    request<{
      id: string;
      dur_screening_hours: number;
      dur_randomization_hours: number;
      dur_follow_up_hours: number;
      dur_other_hours: number;
      util_threshold_green_max: number;
      util_threshold_amber_max: number;
      default_grid_weeks_visible: number;
      default_horizon_months: number;
      default_site_hours_per_day: number;
      default_attrition_curve_id: string | null;
      currency: string;
    }>("/org-settings"),
  patchOrgSettings: (payload: Record<string, unknown>) =>
    request<{ id: string }>("/org-settings", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};
