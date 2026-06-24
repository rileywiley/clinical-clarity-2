/**
 * New-org onboarding flow (PRD §9.2 Phase 6, §2 goal #3).
 *
 * 3 steps, all skippable:
 *   1. Add your first site
 *   2. Create your first trial (links into /trials/new)
 *   3. Add a teammate (skippable)
 *
 * Reached via /onboarding. Doesn't gate anything — a user can always click
 * "Skip to dashboard" at any step. The goal is a frictionless first 5 minutes
 * for a fresh org.
 */

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Me } from "../api";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

const STEPS = ["site", "trial", "team"] as const;
type Step = (typeof STEPS)[number];

function isStep(s: string | null): s is Step {
  return (STEPS as readonly string[]).includes(s ?? "");
}

export default function Onboarding({ me }: { me: Me }) {
  useDocumentTitle("Welcome");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const step: Step = isStep(params.get("step")) ? (params.get("step") as Step) : "site";

  function goTo(next: Step) {
    setParams({ step: next });
  }
  function finish() {
    navigate("/");
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Welcome, {me.name.split(" ")[0]} 👋</h1>
        <p className="text-sm text-slate-500">
          Three quick steps to get the forecast working with your data.
        </p>
      </header>

      <ol className="flex gap-2" aria-label="Onboarding steps">
        {STEPS.map((s, i) => {
          const isCurrent = s === step;
          return (
            <li key={s}>
              <button
                type="button"
                onClick={() => goTo(s)}
                className={`rounded border px-3 py-1.5 text-sm ${
                  isCurrent
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                }`}
                data-testid={`onboard-step-${s}`}
              >
                {i + 1}. {labelFor(s)}
              </button>
            </li>
          );
        })}
        <li className="ml-auto">
          <button
            type="button"
            onClick={finish}
            className="rounded border border-slate-200 px-3 py-1.5 text-sm text-slate-500"
            data-testid="onboard-skip"
          >
            Skip to dashboard
          </button>
        </li>
      </ol>

      {step === "site" && <SiteStep onContinue={() => goTo("trial")} />}
      {step === "trial" && <TrialStep onContinue={() => goTo("team")} />}
      {step === "team" && <TeamStep onContinue={finish} />}
    </div>
  );
}

function labelFor(s: Step): string {
  switch (s) {
    case "site":
      return "First site";
    case "trial":
      return "First trial";
    case "team":
      return "Invite teammates";
  }
}

// --- Step 1: site -------------------------------------------------------

function SiteStep({ onContinue }: { onContinue: () => void }) {
  const qc = useQueryClient();
  const sitesQ = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const [form, setForm] = useState({
    name: "",
    timezone: "America/New_York",
    hours_per_day: 10,
    rooms: 1,
  });
  const [status, setStatus] = useState<"idle" | "saving" | "error">("idle");

  async function save() {
    setStatus("saving");
    try {
      const res = await fetch("/api/sites", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name,
          timezone: form.timezone,
          operating_weekdays: [0, 1, 2, 3, 4],
          hours_per_day: form.hours_per_day,
          rooms: form.rooms,
        }),
      });
      if (!res.ok) throw new Error("create failed");
      await qc.invalidateQueries({ queryKey: ["sites"] });
      onContinue();
    } catch {
      setStatus("error");
    }
  }

  const existingCount = (sitesQ.data ?? []).length;
  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-base font-semibold">Add your first site</h2>
      <p className="mb-3 text-sm text-slate-500">
        A site is one physical location with rooms and operating hours. You can
        add more later under the network grid.
      </p>
      {existingCount > 0 && (
        <p className="mb-3 rounded border border-emerald-200 bg-emerald-50 p-2 text-sm text-emerald-900">
          You already have {existingCount} site{existingCount === 1 ? "" : "s"}.
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm">
          <span className="block text-xs font-medium text-slate-600">Site name</span>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1.5"
            data-testid="onboard-site-name"
          />
        </label>
        <label className="text-sm">
          <span className="block text-xs font-medium text-slate-600">Timezone (IANA)</span>
          <input
            type="text"
            value={form.timezone}
            onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
            className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="text-sm">
          <span className="block text-xs font-medium text-slate-600">Rooms</span>
          <input
            type="number"
            min={1}
            value={form.rooms}
            onChange={(e) => setForm((f) => ({ ...f, rooms: Number(e.target.value) }))}
            className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="text-sm">
          <span className="block text-xs font-medium text-slate-600">Hours per day</span>
          <input
            type="number"
            min={1}
            max={24}
            value={form.hours_per_day}
            onChange={(e) =>
              setForm((f) => ({ ...f, hours_per_day: Number(e.target.value) }))
            }
            className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
      </div>
      {status === "error" && (
        <p className="mt-2 text-sm text-red-700">Couldn't save the site.</p>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onContinue}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm"
        >
          Skip
        </button>
        <button
          type="button"
          onClick={save}
          disabled={status === "saving" || !form.name}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          data-testid="onboard-site-save"
        >
          {status === "saving" ? "Saving…" : "Save & continue"}
        </button>
      </div>
    </section>
  );
}

// --- Step 2: trial — deep-link into the wizard --------------------------

function TrialStep({ onContinue }: { onContinue: () => void }) {
  const trialsQ = useQuery({ queryKey: ["trials"], queryFn: api.listTrials });
  const existing = trialsQ.data ?? [];
  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-base font-semibold">Create your first trial</h2>
      <p className="mb-3 text-sm text-slate-500">
        The trial setup wizard walks you through basics, the SoA (upload your
        protocol PDF and Claude will extract it), sites, pricing, and attrition.
      </p>
      {existing.length > 0 && (
        <p className="mb-3 rounded border border-emerald-200 bg-emerald-50 p-2 text-sm text-emerald-900">
          You already have {existing.length} trial{existing.length === 1 ? "" : "s"}.
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onContinue}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm"
        >
          Skip
        </button>
        <Link
          to="/trials/new"
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white"
          data-testid="onboard-trial-open-wizard"
        >
          Open trial setup →
        </Link>
      </div>
    </section>
  );
}

// --- Step 3: team -------------------------------------------------------

function TeamStep({ onContinue }: { onContinue: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );

  async function invite() {
    setStatus("saving");
    try {
      await api.createUser({
        name: form.name,
        email: form.email,
        password: form.password,
        role: "viewer",
      });
      setForm({ name: "", email: "", password: "" });
      await qc.invalidateQueries({ queryKey: ["users"] });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-base font-semibold">Invite teammates (optional)</h2>
      <p className="mb-3 text-sm text-slate-500">
        Add a Viewer now if you'd like someone to follow along. You can change
        roles and add more under Admin settings later.
      </p>
      <div className="grid gap-2 md:grid-cols-3">
        <input
          type="text"
          placeholder="Name"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          className="rounded border border-slate-300 px-2 py-1.5 text-sm"
        />
        <input
          type="email"
          placeholder="Email"
          value={form.email}
          onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
          className="rounded border border-slate-300 px-2 py-1.5 text-sm"
        />
        <input
          type="password"
          placeholder="Temp password (≥8 chars)"
          value={form.password}
          onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
          className="rounded border border-slate-300 px-2 py-1.5 text-sm"
        />
      </div>
      {status === "saved" && (
        <p className="mt-2 text-sm text-emerald-700">✓ Invited.</p>
      )}
      {status === "error" && (
        <p className="mt-2 text-sm text-red-700">Couldn't invite.</p>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={invite}
          disabled={
            status === "saving" ||
            !form.name ||
            !form.email ||
            form.password.length < 8
          }
          className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
          data-testid="onboard-team-invite"
        >
          {status === "saving" ? "Inviting…" : "Invite & continue"}
        </button>
        <button
          type="button"
          onClick={onContinue}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white"
          data-testid="onboard-finish"
        >
          Finish →
        </button>
      </div>
    </section>
  );
}
