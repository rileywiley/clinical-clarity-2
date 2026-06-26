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
import { ApiError, api, type Me, type SiteOut } from "../api";
import { ThemeToggle } from "../components/ThemeToggle";
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
      <Appearance />
      <DisplayDefaults />
      <OrgDefaults />
      <SiteManagement />
      <UserManagement />
      <DangerZone />
    </div>
  );
}

// --- Appearance (theme) -------------------------------------------------

function Appearance() {
  return (
    <Section
      title="Appearance"
      hint="Light or dark theme. Saved in this browser (per-device, not org-wide)."
    >
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-600">Theme</span>
        <ThemeToggle />
      </div>
    </Section>
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

function LabeledInput({
  label,
  value,
  onChange,
  type = "text",
  dataTestid,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  dataTestid?: string;
}) {
  return (
    <label className="text-sm">
      <span className="block text-xs font-medium text-slate-600">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1.5"
        data-testid={dataTestid}
      />
    </label>
  );
}

// --- Site management — edit site details --------------------------------

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function fmtDays(days: number[]): string {
  return days.length === 0
    ? "—"
    : [...days].sort((a, b) => a - b).map((d) => DAY_LABELS[d]).join(" ");
}

function SiteManagement() {
  const sitesQ = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const [editing, setEditing] = useState<SiteOut | null>(null);
  const sites = sitesQ.data ?? [];

  return (
    <Section
      title="Sites"
      hint="Edit a site's capacity (rooms, hours/day, operating days), timezone, address, or active state. Capacity changes re-flow live to the forecast."
    >
      {sitesQ.isLoading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : sites.length === 0 ? (
        <p className="text-sm text-slate-500">No sites in this org yet.</p>
      ) : (
        <div className="overflow-x-auto rounded border border-slate-200">
          <table className="w-full text-sm" data-testid="site-management-table">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">Site</th>
                <th className="px-3 py-2">Timezone</th>
                <th className="px-3 py-2 text-right">Rooms</th>
                <th className="px-3 py-2 text-right">Hours/day</th>
                <th className="px-3 py-2">Days</th>
                <th className="px-3 py-2">Active</th>
                <th className="px-3 py-2 text-right">Edit</th>
              </tr>
            </thead>
            <tbody>
              {sites.map((s) => (
                <tr key={s.id} className="border-t border-slate-100">
                  <td className="px-3 py-1.5 font-medium text-slate-800">{s.name}</td>
                  <td className="px-3 py-1.5 text-slate-600">{s.timezone}</td>
                  <td className="px-3 py-1.5 text-right">{s.rooms}</td>
                  <td className="px-3 py-1.5 text-right">{s.hours_per_day}</td>
                  <td className="px-3 py-1.5 text-slate-600">{fmtDays(s.operating_weekdays)}</td>
                  <td className="px-3 py-1.5 text-slate-600">{s.active ? "Yes" : "No"}</td>
                  <td className="px-3 py-1.5 text-right">
                    <button
                      type="button"
                      onClick={() => setEditing(s)}
                      className="rounded border border-slate-300 px-2 py-1 text-xs"
                      data-testid={`site-edit-${s.id}`}
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <EditSiteModal site={editing} onClose={() => setEditing(null)} />
      )}
    </Section>
  );
}

function EditSiteModal({
  site,
  onClose,
}: {
  site: SiteOut;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(site.name);
  const [address, setAddress] = useState(site.address ?? "");
  const [timezone, setTimezone] = useState(site.timezone);
  const [rooms, setRooms] = useState(String(site.rooms));
  const [hours, setHours] = useState(String(site.hours_per_day));
  const [weekdays, setWeekdays] = useState<number[]>(site.operating_weekdays);
  const [active, setActive] = useState(site.active);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function toggleDay(d: number) {
    setWeekdays((w) =>
      w.includes(d) ? w.filter((x) => x !== d) : [...w, d].sort((a, b) => a - b),
    );
  }

  async function save() {
    setErr(null);
    const r = Number(rooms);
    const h = Number(hours);
    if (!Number.isInteger(r) || r < 1) return setErr("Rooms must be a whole number ≥ 1.");
    if (!Number.isFinite(h) || h <= 0 || h > 24) return setErr("Hours/day must be between 1 and 24.");
    if (weekdays.length === 0) return setErr("Pick at least one operating day.");
    if (!name.trim()) return setErr("Name is required.");
    if (!timezone.trim()) return setErr("Timezone is required.");

    setSaving(true);
    try {
      await api.patchSite(site.id, {
        name: name.trim(),
        address: address.trim() || null,
        timezone: timezone.trim(),
        operating_weekdays: weekdays,
        hours_per_day: h,
        rooms: r,
        active,
      });
      // Capacity inputs feed the engine — refresh sites + every forecast view.
      qc.invalidateQueries({ queryKey: ["sites"] });
      qc.invalidateQueries({ queryKey: ["forecast-network"] });
      qc.invalidateQueries({ queryKey: ["site-forecast", site.id] });
      onClose();
    } catch (e) {
      setErr(
        e instanceof ApiError
          ? `Save failed (${e.status}).`
          : "Save failed. Check the values and try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4"
      data-testid="edit-site-modal"
    >
      <div className="w-full max-w-lg rounded-lg bg-white p-5 shadow-lg">
        <h3 className="mb-3 text-base font-semibold text-slate-900">
          Edit site — {site.name}
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <LabeledInput label="Name" value={name} onChange={setName} dataTestid="site-name" />
          <LabeledInput label="Timezone (IANA)" value={timezone} onChange={setTimezone} dataTestid="site-tz" />
          <LabeledInput label="Address" value={address} onChange={setAddress} dataTestid="site-address" />
          <LabeledInput label="Rooms" type="number" value={rooms} onChange={setRooms} dataTestid="site-rooms" />
          <LabeledInput label="Hours / day" type="number" value={hours} onChange={setHours} dataTestid="site-hours" />
          <label className="flex items-end gap-2 text-sm">
            <input
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
              data-testid="site-active"
            />
            <span className="mb-0.5 text-slate-700">Active</span>
          </label>
        </div>

        <div className="mt-3">
          <span className="mb-1 block text-xs font-medium text-slate-600">
            Operating days
          </span>
          <div className="flex flex-wrap gap-1.5" data-testid="site-weekdays">
            {DAY_LABELS.map((label, d) => {
              const on = weekdays.includes(d);
              return (
                <button
                  key={d}
                  type="button"
                  onClick={() => toggleDay(d)}
                  aria-pressed={on}
                  className={
                    "rounded border px-2 py-1 text-xs " +
                    (on
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-300 bg-white text-slate-700")
                  }
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {err && (
          <p className="mt-3 rounded border border-amber-200 bg-amber-50 p-2 text-sm text-amber-900">
            {err}
          </p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            data-testid="site-save-button"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

// --- 5. Danger zone — delete sites & studies ----------------------------

function DangerZone() {
  const sitesQ = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const trialsQ = useQuery({ queryKey: ["trials"], queryFn: api.listTrials });
  const [pending, setPending] = useState<
    | { kind: "site"; id: string; name: string }
    | { kind: "trial"; id: string; name: string; status: string }
    | null
  >(null);

  return (
    <Section
      title="Danger zone"
      hint="Permanently delete sites and studies. Deletes cascade — sites take their assignments + projection weeks; trials take their arms, visits, assignments, weeks, and snapshot history. There is no undo."
    >
      <div className="space-y-5">
        <DeleteTable
          title="Sites"
          rows={(sitesQ.data ?? []).map((s) => ({
            id: s.id,
            name: s.name,
            sub: s.timezone,
            disabled: false,
          }))}
          emptyText="No sites in this org."
          onDelete={(row) =>
            setPending({ kind: "site", id: row.id, name: row.name })
          }
          dataTestidPrefix="danger-site"
        />

        <DeleteTable
          title="Studies"
          rows={(trialsQ.data ?? []).map((t) => ({
            id: t.id,
            name: t.name,
            sub: t.status,
            disabled: false,
          }))}
          emptyText="No trials in this org."
          onDelete={(row) => {
            const t = (trialsQ.data ?? []).find((x) => x.id === row.id)!;
            setPending({
              kind: "trial",
              id: t.id,
              name: t.name,
              status: t.status,
            });
          }}
          dataTestidPrefix="danger-trial"
        />
      </div>

      {pending?.kind === "site" && (
        <DeleteSiteModal
          siteId={pending.id}
          siteName={pending.name}
          onClose={() => setPending(null)}
        />
      )}
      {pending?.kind === "trial" && (
        <DeleteTrialModal
          trialId={pending.id}
          trialName={pending.name}
          trialStatus={pending.status}
          onClose={() => setPending(null)}
        />
      )}
    </Section>
  );
}

function DeleteTable({
  title,
  rows,
  emptyText,
  onDelete,
  dataTestidPrefix,
}: {
  title: string;
  rows: Array<{ id: string; name: string; sub: string; disabled: boolean }>;
  emptyText: string;
  onDelete: (row: { id: string; name: string }) => void;
  dataTestidPrefix: string;
}) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium text-slate-700">{title}</h3>
      <div className="overflow-x-auto rounded border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">&nbsp;</th>
              <th className="px-3 py-2 text-right">&nbsp;</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={3} className="px-3 py-4 text-center text-slate-500">
                  {emptyText}
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100">
                <td className="px-3 py-1.5">{r.name}</td>
                <td className="px-3 py-1.5 text-xs text-slate-500">{r.sub}</td>
                <td className="px-3 py-1.5 text-right">
                  <button
                    type="button"
                    onClick={() => onDelete(r)}
                    disabled={r.disabled}
                    className="rounded border border-red-300 bg-white px-2 py-0.5 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40"
                    data-testid={`${dataTestidPrefix}-delete-${r.id}`}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DeleteSiteModal({
  siteId,
  siteName,
  onClose,
}: {
  siteId: string;
  siteName: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const impactQ = useQuery({
    queryKey: ["site-delete-impact", siteId],
    queryFn: () => api.getSiteDeleteImpact(siteId),
  });
  const [typed, setTyped] = useState("");
  const [status, setStatus] = useState<"idle" | "deleting" | "error">("idle");
  const [errorText, setErrorText] = useState<string | null>(null);

  async function doDelete() {
    setStatus("deleting");
    setErrorText(null);
    try {
      await api.deleteSite(siteId);
      qc.invalidateQueries({ queryKey: ["sites"] });
      qc.invalidateQueries({ queryKey: ["trials"] });
      qc.invalidateQueries({ queryKey: ["forecast-network"] });
      qc.invalidateQueries({ queryKey: ["site-forecast"] });
      onClose();
    } catch (err) {
      setStatus("error");
      setErrorText(err instanceof Error ? err.message : "Delete failed.");
    }
  }

  return (
    <ConfirmModal
      title={`Delete site "${siteName}"?`}
      confirmDisabled={typed !== siteName || status === "deleting"}
      confirmLabel={status === "deleting" ? "Deleting…" : "Delete"}
      onConfirm={doDelete}
      onClose={onClose}
      dataTestid="danger-site-modal"
    >
      {impactQ.data ? (
        <ImpactList
          rows={[
            ["Trial assignments", impactQ.data.trial_assignments],
            ["Projection weeks", impactQ.data.enrollment_weeks],
            ["User assignments", impactQ.data.user_assignments],
          ]}
        />
      ) : (
        <p className="text-sm text-slate-500">Loading impact…</p>
      )}
      <TypeToConfirm
        expected={siteName}
        value={typed}
        onChange={setTyped}
        dataTestid="danger-site-type-confirm"
      />
      {errorText && (
        <p className="mt-2 text-sm text-red-700">{errorText}</p>
      )}
    </ConfirmModal>
  );
}

function DeleteTrialModal({
  trialId,
  trialName,
  trialStatus,
  onClose,
}: {
  trialId: string;
  trialName: string;
  trialStatus: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const impactQ = useQuery({
    queryKey: ["trial-delete-impact", trialId],
    queryFn: () => api.getTrialDeleteImpact(trialId),
  });
  const [typed, setTyped] = useState("");
  const [status, setStatus] = useState<"idle" | "deleting" | "archiving" | "error">(
    "idle",
  );
  const [errorText, setErrorText] = useState<string | null>(null);

  const isActive = (impactQ.data?.status ?? trialStatus) === "active";

  async function archive() {
    setStatus("archiving");
    setErrorText(null);
    try {
      await api.archiveTrial(trialId);
      qc.invalidateQueries({ queryKey: ["trials"] });
      qc.invalidateQueries({ queryKey: ["trial-delete-impact", trialId] });
      qc.invalidateQueries({ queryKey: ["forecast-network"] });
      setStatus("idle");
    } catch (err) {
      setStatus("error");
      setErrorText(err instanceof Error ? err.message : "Archive failed.");
    }
  }

  async function doDelete() {
    setStatus("deleting");
    setErrorText(null);
    try {
      await api.deleteTrial(trialId);
      qc.invalidateQueries({ queryKey: ["trials"] });
      qc.invalidateQueries({ queryKey: ["forecast-network"] });
      qc.invalidateQueries({ queryKey: ["site-forecast"] });
      qc.invalidateQueries({ queryKey: ["trials-active"] });
      onClose();
    } catch (err) {
      setStatus("error");
      setErrorText(err instanceof Error ? err.message : "Delete failed.");
    }
  }

  return (
    <ConfirmModal
      title={`Delete trial "${trialName}"?`}
      confirmDisabled={
        isActive || typed !== trialName || status === "deleting"
      }
      confirmLabel={status === "deleting" ? "Deleting…" : "Delete"}
      onConfirm={doDelete}
      onClose={onClose}
      dataTestid="danger-trial-modal"
    >
      {isActive && (
        <div
          className="mb-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          data-testid="danger-trial-active-block"
        >
          <strong>This trial is active.</strong> Active trials can't be deleted —
          archive first to avoid silently wiping live forecast contribution.
          <div className="mt-2">
            <button
              type="button"
              onClick={archive}
              disabled={status === "archiving"}
              className="rounded border border-amber-400 bg-white px-2 py-0.5 text-xs text-amber-900 disabled:opacity-40"
              data-testid="danger-trial-archive"
            >
              {status === "archiving" ? "Archiving…" : "Archive now"}
            </button>
          </div>
        </div>
      )}
      {impactQ.data ? (
        <ImpactList
          rows={[
            ["Arms", impactQ.data.arms],
            ["Visits (SoA rows)", impactQ.data.visits],
            ["Site assignments", impactQ.data.site_assignments],
            ["Projection weeks", impactQ.data.enrollment_weeks],
            ["SoA snapshots", impactQ.data.soa_snapshots],
          ]}
        />
      ) : (
        <p className="text-sm text-slate-500">Loading impact…</p>
      )}
      {!isActive && (
        <TypeToConfirm
          expected={trialName}
          value={typed}
          onChange={setTyped}
          dataTestid="danger-trial-type-confirm"
        />
      )}
      {errorText && (
        <p className="mt-2 text-sm text-red-700">{errorText}</p>
      )}
    </ConfirmModal>
  );
}

function ImpactList({ rows }: { rows: Array<[string, number]> }) {
  return (
    <ul className="mb-3 list-disc space-y-0.5 pl-5 text-sm text-slate-700">
      {rows.map(([label, n]) => (
        <li key={label} className={n > 0 ? "" : "text-slate-400"}>
          {label}: <strong>{n}</strong>
        </li>
      ))}
    </ul>
  );
}

function TypeToConfirm({
  expected,
  value,
  onChange,
  dataTestid,
}: {
  expected: string;
  value: string;
  onChange: (s: string) => void;
  dataTestid?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="block text-xs font-medium text-slate-600">
        Type <code className="rounded bg-slate-100 px-1 text-xs">{expected}</code>{" "}
        to confirm:
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1.5 font-mono"
        data-testid={dataTestid}
        autoFocus
      />
    </label>
  );
}

function ConfirmModal({
  title,
  children,
  confirmDisabled,
  confirmLabel,
  onConfirm,
  onClose,
  dataTestid,
}: {
  title: string;
  children: React.ReactNode;
  confirmDisabled: boolean;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  dataTestid?: string;
}) {
  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4"
      data-testid={dataTestid}
    >
      <div className="w-full max-w-lg rounded-lg bg-white p-5 shadow-lg">
        <h3 className="mb-3 text-base font-semibold text-slate-900">{title}</h3>
        {children}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={confirmDisabled}
            className="rounded bg-red-700 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            data-testid="confirm-delete-button"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// --- Shared row helper --------------------------------------------------

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
