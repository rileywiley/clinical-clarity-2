/**
 * Admin Settings (PRD §7.5, §8.6).
 *
 * Four sections, all backed by existing /org-settings PATCH (Phase 2) and
 * new /users endpoints (Phase 6):
 *   1. Forecasting defaults  — visit-type durations + default attrition curve
 *   2. Display defaults      — utilization color thresholds + grid windows
 *   3. Org defaults          — site hours/day
 *   4. User management       — list/create/deactivate users in the org
 *
 * Role-gated to org_admin (non-admin who lands here gets a polite refusal).
 * Each section saves independently — no one big "Save all" button.
 * Duration changes show an inline note: "this will re-flow live to every
 * trial without an explicit override" (PRD §5.2 mitigation made visible).
 */

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Me } from "../api";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function AdminSettings({ me }: { me: Me }) {
  useDocumentTitle("Admin settings");
  if (me.role !== "org_admin") {
    return (
      <div className="mx-auto mt-12 max-w-2xl p-6">
        <h1 className="text-2xl font-semibold">Admin settings</h1>
        <p className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Only Org Admins can view this page.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <nav className="text-sm text-slate-500" aria-label="Breadcrumb">
        <Link to="/" className="hover:underline">
          Network
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">Admin settings</span>
      </nav>
      <h1 className="text-2xl font-semibold">Admin settings</h1>

      <ForecastingDefaults />
      <DisplayDefaults />
      <OrgDefaults />
      <UserManagement />
    </div>
  );
}

// --- 1. Forecasting defaults --------------------------------------------

function ForecastingDefaults() {
  const qc = useQueryClient();
  const sQ = useQuery({ queryKey: ["org-settings"], queryFn: api.getOrgSettings });
  const curvesQ = useQuery({
    queryKey: ["attrition-curves"],
    queryFn: api.listAttritionCurves,
  });

  type Form = {
    dur_screening_hours: number;
    dur_randomization_hours: number;
    dur_follow_up_hours: number;
    dur_other_hours: number;
    default_attrition_curve_id: string;
  };
  const [form, setForm] = useState<Form | null>(null);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  useEffect(() => {
    if (!sQ.data) return;
    setForm({
      dur_screening_hours: Number(sQ.data.dur_screening_hours),
      dur_randomization_hours: Number(sQ.data.dur_randomization_hours),
      dur_follow_up_hours: Number(sQ.data.dur_follow_up_hours),
      dur_other_hours: Number(sQ.data.dur_other_hours),
      default_attrition_curve_id: sQ.data.default_attrition_curve_id ?? "",
    });
  }, [sQ.data]);

  async function save() {
    if (!form) return;
    setStatus("saving");
    try {
      await api.patchOrgSettings({
        ...form,
        default_attrition_curve_id: form.default_attrition_curve_id || null,
      });
      await qc.invalidateQueries({ queryKey: ["org-settings"] });
      await qc.invalidateQueries({ queryKey: ["forecast-network"] });
      await qc.invalidateQueries({ queryKey: ["site-forecast"] });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  if (!form) return <SectionSkeleton title="Forecasting defaults" />;

  return (
    <Section
      title="Forecasting defaults"
      hint="Visit-type durations resolve live — changing a value here re-flows to every trial that hasn't set an explicit override (PRD §5.2)."
    >
      <div className="grid gap-3 md:grid-cols-2">
        <NumField
          label="Screening duration (hr)"
          value={form.dur_screening_hours}
          onChange={(v) => setForm((f) => f && { ...f, dur_screening_hours: v })}
          dataTestid="dur-screening"
        />
        <NumField
          label="Randomization duration (hr)"
          value={form.dur_randomization_hours}
          onChange={(v) => setForm((f) => f && { ...f, dur_randomization_hours: v })}
          dataTestid="dur-randomization"
        />
        <NumField
          label="Follow-up duration (hr)"
          value={form.dur_follow_up_hours}
          onChange={(v) => setForm((f) => f && { ...f, dur_follow_up_hours: v })}
          dataTestid="dur-follow-up"
        />
        <NumField
          label="Other duration (hr)"
          value={form.dur_other_hours}
          onChange={(v) => setForm((f) => f && { ...f, dur_other_hours: v })}
          dataTestid="dur-other"
        />
        <label className="text-sm md:col-span-2">
          <span className="block text-xs font-medium text-slate-600">
            Default attrition curve for new trials
          </span>
          <select
            value={form.default_attrition_curve_id}
            onChange={(e) =>
              setForm((f) => f && { ...f, default_attrition_curve_id: e.target.value })
            }
            className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1.5"
            data-testid="default-attrition"
          >
            <option value="">(none)</option>
            {(curvesQ.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({(c.total_dropout_pct * 100).toFixed(0)}%)
              </option>
            ))}
          </select>
        </label>
      </div>
      <SaveRow status={status} onSave={save} dataTestid="forecasting-save" />
    </Section>
  );
}

// --- 2. Display defaults ------------------------------------------------

function DisplayDefaults() {
  const qc = useQueryClient();
  const sQ = useQuery({ queryKey: ["org-settings"], queryFn: api.getOrgSettings });
  type Form = {
    util_threshold_green_max: number;
    util_threshold_amber_max: number;
    default_grid_weeks_visible: number;
    default_horizon_months: number;
  };
  const [form, setForm] = useState<Form | null>(null);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  useEffect(() => {
    if (!sQ.data) return;
    setForm({
      util_threshold_green_max: Number(sQ.data.util_threshold_green_max),
      util_threshold_amber_max: Number(sQ.data.util_threshold_amber_max),
      default_grid_weeks_visible: sQ.data.default_grid_weeks_visible,
      default_horizon_months: sQ.data.default_horizon_months,
    });
  }, [sQ.data]);

  async function save() {
    if (!form) return;
    if (form.util_threshold_green_max >= form.util_threshold_amber_max) {
      setStatus("error");
      return;
    }
    setStatus("saving");
    try {
      await api.patchOrgSettings(form);
      await qc.invalidateQueries({ queryKey: ["org-settings"] });
      await qc.invalidateQueries({ queryKey: ["forecast-network"] });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  if (!form) return <SectionSkeleton title="Display defaults" />;

  return (
    <Section
      title="Display defaults"
      hint="Color thresholds apply to every utilization cell in the network grid and calendar."
    >
      <div className="grid gap-3 md:grid-cols-2">
        <NumField
          label="Green ≤ this utilization %"
          value={form.util_threshold_green_max}
          onChange={(v) => setForm((f) => f && { ...f, util_threshold_green_max: v })}
          dataTestid="util-green"
        />
        <NumField
          label="Amber ≤ this utilization %"
          value={form.util_threshold_amber_max}
          onChange={(v) => setForm((f) => f && { ...f, util_threshold_amber_max: v })}
          dataTestid="util-amber"
        />
        <NumField
          label="Default grid weeks visible"
          value={form.default_grid_weeks_visible}
          onChange={(v) =>
            setForm((f) => f && { ...f, default_grid_weeks_visible: v })
          }
          dataTestid="grid-weeks"
        />
        <NumField
          label="Default forecast horizon (months)"
          value={form.default_horizon_months}
          onChange={(v) => setForm((f) => f && { ...f, default_horizon_months: v })}
          dataTestid="horizon-months"
        />
      </div>
      {form.util_threshold_green_max >= form.util_threshold_amber_max && (
        <p className="mt-2 text-sm text-red-700">
          Green threshold must be lower than amber threshold.
        </p>
      )}
      <SaveRow status={status} onSave={save} dataTestid="display-save" />
    </Section>
  );
}

// --- 3. Org defaults ----------------------------------------------------

function OrgDefaults() {
  const qc = useQueryClient();
  const sQ = useQuery({ queryKey: ["org-settings"], queryFn: api.getOrgSettings });
  const [hours, setHours] = useState<number | null>(null);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  useEffect(() => {
    if (sQ.data) setHours(Number(sQ.data.default_site_hours_per_day));
  }, [sQ.data]);

  async function save() {
    if (hours == null) return;
    setStatus("saving");
    try {
      await api.patchOrgSettings({ default_site_hours_per_day: hours });
      await qc.invalidateQueries({ queryKey: ["org-settings"] });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  if (hours == null) return <SectionSkeleton title="Org defaults" />;

  return (
    <Section
      title="Org defaults"
      hint="Used when a new site is created without specifying its own hours per day."
    >
      <div className="grid max-w-md gap-3">
        <NumField
          label="Default site hours per day"
          value={hours}
          onChange={setHours}
          dataTestid="default-site-hours"
        />
      </div>
      <SaveRow status={status} onSave={save} dataTestid="org-defaults-save" />
    </Section>
  );
}

// --- 4. User management -------------------------------------------------

function UserManagement() {
  const qc = useQueryClient();
  const usersQ = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const [form, setForm] = useState({
    email: "",
    name: "",
    password: "",
    role: "viewer" as Me["role"],
  });
  const [createStatus, setCreateStatus] = useState<"idle" | "saving" | "error">("idle");
  const [createError, setCreateError] = useState<string | null>(null);

  async function create() {
    setCreateStatus("saving");
    setCreateError(null);
    try {
      await api.createUser(form);
      setForm({ email: "", name: "", password: "", role: "viewer" });
      await qc.invalidateQueries({ queryKey: ["users"] });
      setCreateStatus("idle");
    } catch (e) {
      setCreateStatus("error");
      setCreateError(e instanceof Error ? e.message : "create failed");
    }
  }

  async function toggleActive(userId: string, active: boolean) {
    try {
      await api.patchUser(userId, { active });
      await qc.invalidateQueries({ queryKey: ["users"] });
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "patch failed");
    }
  }

  async function changeRole(userId: string, role: Me["role"]) {
    try {
      await api.patchUser(userId, { role });
      await qc.invalidateQueries({ queryKey: ["users"] });
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "patch failed");
    }
  }

  return (
    <Section
      title="User management"
      hint="Add teammates, change roles, deactivate. Site-scoped role assignments live on each site's detail page."
    >
      <div className="rounded border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Email</th>
              <th className="px-3 py-2">Role</th>
              <th className="px-3 py-2">Active</th>
            </tr>
          </thead>
          <tbody>
            {(usersQ.data ?? []).map((u) => (
              <tr
                key={u.id}
                className="border-t border-slate-100"
                data-testid={`user-row-${u.id}`}
              >
                <td className="px-3 py-1.5">{u.name}</td>
                <td className="px-3 py-1.5 text-slate-600">{u.email}</td>
                <td className="px-3 py-1.5">
                  <select
                    value={u.role}
                    onChange={(e) => changeRole(u.id, e.target.value as Me["role"])}
                    className="rounded border border-slate-300 px-2 py-1 text-sm"
                  >
                    <option value="org_admin">Org Admin</option>
                    <option value="ops_lead">Ops Lead</option>
                    <option value="site_manager">Site Manager</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </td>
                <td className="px-3 py-1.5">
                  <input
                    type="checkbox"
                    checked={u.active}
                    onChange={(e) => toggleActive(u.id, e.target.checked)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 rounded border border-slate-200 bg-slate-50 p-3">
        <h3 className="mb-2 text-sm font-medium">Invite a teammate</h3>
        <div className="grid gap-2 md:grid-cols-4">
          <input
            type="text"
            placeholder="Name"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            data-testid="invite-name"
          />
          <input
            type="email"
            placeholder="Email"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            data-testid="invite-email"
          />
          <input
            type="password"
            placeholder="Temp password (≥8 chars)"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            data-testid="invite-password"
          />
          <div className="flex gap-2">
            <select
              value={form.role}
              onChange={(e) =>
                setForm((f) => ({ ...f, role: e.target.value as Me["role"] }))
              }
              className="flex-1 rounded border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value="org_admin">Org Admin</option>
              <option value="ops_lead">Ops Lead</option>
              <option value="site_manager">Site Manager</option>
              <option value="viewer">Viewer</option>
            </select>
            <button
              type="button"
              onClick={create}
              disabled={
                createStatus === "saving" ||
                !form.email ||
                !form.name ||
                form.password.length < 8
              }
              className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
              data-testid="invite-submit"
            >
              {createStatus === "saving" ? "Adding…" : "Add"}
            </button>
          </div>
        </div>
        {createError && (
          <p className="mt-2 text-sm text-red-700">{createError}</p>
        )}
      </div>
    </Section>
  );
}

// --- Section helpers ----------------------------------------------------

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <h2 className="text-base font-semibold">{title}</h2>
      {hint && <p className="mb-3 text-sm text-slate-500">{hint}</p>}
      {children}
    </section>
  );
}

function SectionSkeleton({ title }: { title: string }) {
  return (
    <Section title={title}>
      <p className="text-sm text-slate-500">Loading…</p>
    </Section>
  );
}

function NumField({
  label,
  value,
  onChange,
  dataTestid,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  dataTestid?: string;
}) {
  return (
    <label className="text-sm">
      <span className="block text-xs font-medium text-slate-600">{label}</span>
      <input
        type="number"
        min={0}
        step={0.5}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1.5"
        data-testid={dataTestid}
      />
    </label>
  );
}

function SaveRow({
  status,
  onSave,
  dataTestid,
}: {
  status: "idle" | "saving" | "saved" | "error";
  onSave: () => void;
  dataTestid?: string;
}) {
  return (
    <div className="mt-4 flex items-center justify-end gap-3">
      {status === "saved" && (
        <span className="text-xs text-emerald-700">✓ Saved — re-flowing to forecasts.</span>
      )}
      {status === "error" && (
        <span className="text-xs text-red-700">Save failed.</span>
      )}
      <button
        type="button"
        onClick={onSave}
        disabled={status === "saving"}
        className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
        data-testid={dataTestid}
      >
        {status === "saving" ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
