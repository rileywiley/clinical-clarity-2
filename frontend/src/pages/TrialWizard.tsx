/**
 * Trial setup wizard (PRD §7.1, Phase 5).
 *
 * Mounted at /trials/new. URL-driven step:
 *   ?step=basics
 *   ?step=soa&trialId=...
 *   ?step=sites&trialId=...
 *   ?step=pricing&trialId=...
 *   ?step=attrition&trialId=...
 *   ?step=activate&trialId=...
 *
 * After Basics saves the trial, every step is resumable by URL — refresh,
 * deep-link, or click into a completed step from the progress strip.
 *
 * Each step uses useUnsavedChangesGuard so leaving with unsaved input
 * blocks via browser-native confirm (per saved feedback memory).
 */

import { useEffect, useMemo, useState } from "react";
import {
  Link,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  api,
  type ParsedVisitOut,
  type SoaParseJobOut,
} from "../api";
import { SoaReviewTable } from "../components/SoaReviewTable";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";

const STEPS = [
  { id: "basics", label: "Basics" },
  { id: "soa", label: "Schedule of activities" },
  { id: "sites", label: "Sites & targets" },
  { id: "pricing", label: "Visit pricing" },
  { id: "attrition", label: "Attrition" },
  { id: "activate", label: "Activate" },
] as const;

type StepId = (typeof STEPS)[number]["id"];

function isValidStep(s: string | null): s is StepId {
  return STEPS.some((step) => step.id === s);
}

export default function TrialWizard() {
  const [params, setParams] = useSearchParams();
  const stepParam = params.get("step");
  const step: StepId = isValidStep(stepParam) ? stepParam : "basics";
  const trialId = params.get("trialId");

  // Force step=basics on first load (or if URL is missing it).
  useEffect(() => {
    if (!isValidStep(stepParam)) {
      setParams({ step: "basics" }, { replace: true });
    }
  }, [stepParam, setParams]);

  function goToStep(next: StepId) {
    const p = new URLSearchParams(params);
    p.set("step", next);
    setParams(p);
  }

  // Determine which steps are reachable: basics is always; everything else
  // needs a trialId.
  const reachable: Record<StepId, boolean> = {
    basics: true,
    soa: !!trialId,
    sites: !!trialId,
    pricing: !!trialId,
    attrition: !!trialId,
    activate: !!trialId,
  };

  return (
    <div className="mx-auto max-w-5xl p-6">
      <nav className="mb-4 text-sm text-slate-500" aria-label="Breadcrumb">
        <Link to="/" className="hover:underline">
          Network
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">New trial</span>
      </nav>

      <header className="mb-4">
        <h1 className="text-2xl font-semibold">Set up a trial</h1>
        <p className="text-sm text-slate-500">
          Fill in basics, then come back to the rest in any order.
        </p>
      </header>

      <ol className="mb-6 flex flex-wrap gap-2" aria-label="Steps">
        {STEPS.map((s) => {
          const isCurrent = s.id === step;
          const isReachable = reachable[s.id];
          return (
            <li key={s.id}>
              <button
                type="button"
                disabled={!isReachable}
                onClick={() => goToStep(s.id)}
                className={`rounded border px-3 py-1.5 text-sm ${
                  isCurrent
                    ? "border-slate-900 bg-slate-900 text-white"
                    : isReachable
                      ? "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                      : "border-slate-200 bg-slate-50 text-slate-400"
                }`}
                data-testid={`wizard-step-${s.id}`}
              >
                {s.label}
              </button>
            </li>
          );
        })}
      </ol>

      {step === "basics" && (
        <BasicsStep
          trialId={trialId}
          onSaved={(id) =>
            setParams({ step: "soa", trialId: id }, { replace: true })
          }
        />
      )}
      {step === "soa" && trialId && (
        <SoaStep trialId={trialId} onDone={() => goToStep("sites")} />
      )}
      {step === "sites" && trialId && (
        <SitesStep trialId={trialId} onDone={() => goToStep("pricing")} />
      )}
      {step === "pricing" && trialId && (
        <PricingStep trialId={trialId} onDone={() => goToStep("attrition")} />
      )}
      {step === "attrition" && trialId && (
        <AttritionStep trialId={trialId} onDone={() => goToStep("activate")} />
      )}
      {step === "activate" && trialId && <ActivateStep trialId={trialId} />}
    </div>
  );
}

// ============================================================================
// Step 1: Basics
// ============================================================================

function BasicsStep({
  trialId,
  onSaved,
}: {
  trialId: string | null;
  onSaved: (id: string) => void;
}) {
  const trialsQ = useQuery({
    queryKey: ["trial", trialId],
    queryFn: async () => {
      const all = await api.listTrials();
      return all.find((t) => t.id === trialId) ?? null;
    },
    enabled: !!trialId,
  });

  const [form, setForm] = useState({
    name: "",
    sponsor: "",
    fpfv: "",
    lpfv: "",
    lplv: "",
    enrollment_target: 100,
    screening_target: 125,
  });
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (trialsQ.data) {
      setForm({
        name: trialsQ.data.name,
        sponsor: "",
        fpfv: trialsQ.data.fpfv,
        lpfv: trialsQ.data.lpfv,
        lplv: trialsQ.data.lplv,
        enrollment_target: trialsQ.data.enrollment_target,
        screening_target: trialsQ.data.screening_target,
      });
      setDirty(false);
    }
  }, [trialsQ.data]);

  useUnsavedChangesGuard({ dirty });

  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: async () => {
      if (trialId) {
        return await api.patchTrial(trialId, {
          name: form.name,
          fpfv: form.fpfv,
          lpfv: form.lpfv,
          lplv: form.lplv,
          enrollment_target: form.enrollment_target,
          screening_target: form.screening_target,
        });
      }
      return await api.createTrial({
        name: form.name,
        sponsor: form.sponsor || null,
        fpfv: form.fpfv,
        lpfv: form.lpfv,
        lplv: form.lplv,
        enrollment_target: form.enrollment_target,
        screening_target: form.screening_target,
      });
    },
    onSuccess: (t) => {
      setDirty(false);
      setError(null);
      qc.invalidateQueries({ queryKey: ["trials"] });
      qc.invalidateQueries({ queryKey: ["trials-active"] });
      onSaved(t.id);
    },
    onError: (err: unknown) => {
      const detail =
        err instanceof ApiError && err.body
          ? JSON.stringify((err.body as { detail?: unknown }).detail ?? err.body)
          : "Failed to save.";
      setError(detail);
    },
  });

  function update<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((f) => ({ ...f, [k]: v }));
    setDirty(true);
  }

  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <h2 className="mb-3 text-base font-semibold">Basics</h2>
      <p className="mb-4 text-sm text-slate-500">
        Required up front. Everything else can be done in any order.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Trial name *">
          <input
            type="text"
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1.5"
            data-testid="basics-name"
          />
        </Field>
        <Field label="Sponsor">
          <input
            type="text"
            value={form.sponsor}
            onChange={(e) => update("sponsor", e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1.5"
          />
        </Field>
        <Field label="FPFV (first patient first visit) *">
          <input
            type="date"
            value={form.fpfv}
            onChange={(e) => update("fpfv", e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1.5"
            data-testid="basics-fpfv"
          />
        </Field>
        <Field label="LPFV (last patient first visit) *">
          <input
            type="date"
            value={form.lpfv}
            onChange={(e) => update("lpfv", e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1.5"
            data-testid="basics-lpfv"
          />
        </Field>
        <Field label="LPLV (last patient last visit) *">
          <input
            type="date"
            value={form.lplv}
            onChange={(e) => update("lplv", e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1.5"
            data-testid="basics-lplv"
          />
        </Field>
        <Field label="Randomization target">
          <input
            type="number"
            min={0}
            value={form.enrollment_target}
            onChange={(e) =>
              update("enrollment_target", Number(e.target.value))
            }
            className="w-full rounded border border-slate-300 px-2 py-1.5"
          />
        </Field>
        <Field label="Screening target">
          <input
            type="number"
            min={0}
            value={form.screening_target}
            onChange={(e) =>
              update("screening_target", Number(e.target.value))
            }
            className="w-full rounded border border-slate-300 px-2 py-1.5"
          />
        </Field>
      </div>
      {error && (
        <p className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800">
          {error}
        </p>
      )}
      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={
            save.isPending || !form.name || !form.fpfv || !form.lpfv || !form.lplv
          }
          className="rounded bg-slate-900 px-4 py-1.5 text-sm text-white disabled:opacity-40"
          data-testid="basics-save"
        >
          {save.isPending ? "Saving…" : trialId ? "Save & continue" : "Save & continue"}
        </button>
      </div>
    </section>
  );
}

// ============================================================================
// Step 2: Schedule of Activities — upload, poll, review
// ============================================================================

function SoaStep({ trialId, onDone }: { trialId: string; onDone: () => void }) {
  const armsQ = useQuery({
    queryKey: ["arms", trialId],
    queryFn: () => api.listArms(trialId),
  });
  const armId = armsQ.data?.[0]?.id ?? null;

  const [job, setJob] = useState<SoaParseJobOut | null>(null);
  const [parsedVisits, setParsedVisits] = useState<ParsedVisitOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Poll the parse job until it's terminal.
  useEffect(() => {
    if (!job) return;
    if (
      job.status === "succeeded" ||
      job.status === "failed" ||
      job.status === "applied" ||
      job.status === "discarded"
    ) {
      if (job.status === "succeeded") {
        api
          .getParsedVisits(job.id)
          .then((d) => setParsedVisits(d.parsed_visits ?? []))
          .catch(() => setError("Couldn't load parsed visits."));
      }
      return;
    }
    const t = setTimeout(async () => {
      try {
        const next = await api.getParseJob(job.id);
        setJob(next);
      } catch {
        setError("Lost connection to parse job.");
      }
    }, 2000);
    return () => clearTimeout(t);
  }, [job]);

  const upload = useMutation({
    mutationFn: async (file: File) => api.uploadDocument(trialId, file),
    onSuccess: (j) => {
      setJob(j);
      setParsedVisits(null);
      setError(null);
    },
    onError: (err: unknown) => {
      const detail =
        err instanceof ApiError && err.body
          ? JSON.stringify((err.body as { detail?: unknown }).detail ?? err.body)
          : "Upload failed.";
      setError(detail);
    },
  });

  const apply = useMutation({
    mutationFn: async (visits: ParsedVisitOut[]) => {
      if (!job || !armId) throw new Error("missing job or arm");
      return await api.applyParseJob(job.id, { arm_id: armId, visits });
    },
    onSuccess: () => onDone(),
    onError: () => setError("Failed to save visits."),
  });

  const discard = useMutation({
    mutationFn: async () => {
      if (!job) throw new Error("no job");
      await api.discardParseJob(job.id);
    },
    onSuccess: () => {
      setJob(null);
      setParsedVisits(null);
    },
  });

  const visitsQ = useQuery({
    queryKey: ["visits", armId],
    queryFn: () => api.listVisits(armId!),
    enabled: !!armId,
  });

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) upload.mutate(f);
  }

  return (
    <section className="space-y-4">
      <div className="rounded border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-base font-semibold">
          Schedule of Activities
        </h2>
        <p className="mb-3 text-sm text-slate-500">
          Upload the protocol PDF. Claude will extract the SoA — you'll review
          the result and confirm before any visits are saved.
        </p>

        {!job && (
          <div>
            <input
              type="file"
              accept="application/pdf"
              onChange={onFile}
              data-testid="soa-file-input"
              className="block text-sm"
            />
            <p className="mt-2 text-xs text-slate-500">
              PDF only, up to 20 MB. Manual entry is supported by adding rows
              after upload, or by skipping this step.
            </p>
          </div>
        )}

        {job && (
          <div data-testid="soa-job-status">
            <p className="text-sm">
              Parse job: <span className="font-mono text-xs">{job.id.slice(0, 8)}</span>{" "}
              — status{" "}
              <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">
                {job.status}
              </span>
            </p>
            {(job.status === "queued" || job.status === "running") && (
              <p className="mt-2 text-sm text-slate-500">
                {job.status === "queued"
                  ? "Queued — waiting for a worker…"
                  : "Running — Claude is reading the PDF…"}
              </p>
            )}
            {job.status === "failed" && (
              <p className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800">
                Parse failed: {job.error ?? "unknown error"}
              </p>
            )}
          </div>
        )}

        {error && (
          <p className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800">
            {error}
          </p>
        )}
      </div>

      {job?.status === "succeeded" && parsedVisits !== null && (
        <SoaReviewTable
          initialVisits={parsedVisits}
          onConfirm={async (v) => {
            await apply.mutateAsync(v);
          }}
          onDiscard={() => discard.mutate()}
          saving={apply.isPending}
        />
      )}

      {visitsQ.data && visitsQ.data.length > 0 && (
        <div className="rounded border border-slate-200 bg-white p-4">
          <h3 className="mb-2 text-sm font-medium text-slate-700">
            Saved visits ({visitsQ.data.length})
          </h3>
          <ul className="space-y-1 text-sm">
            {visitsQ.data.map((v) => (
              <li key={v.id} className="flex justify-between text-slate-700">
                <span>
                  {v.name}{" "}
                  <span className="text-xs text-slate-500">({v.visit_type})</span>
                </span>
                <span className="text-slate-500">
                  day {v.target_day_offset}, ±{v.window_days}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              onClick={onDone}
              className="rounded border border-slate-300 px-3 py-1.5 text-sm"
              data-testid="soa-continue"
            >
              Continue →
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

// ============================================================================
// Step 3: Sites & targets — pick from existing sites, assign
// ============================================================================

function SitesStep({ trialId, onDone }: { trialId: string; onDone: () => void }) {
  const sitesQ = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const trialQ = useQuery({
    queryKey: ["trial", trialId],
    queryFn: async () => {
      const all = await api.listTrials();
      return all.find((t) => t.id === trialId) ?? null;
    },
  });
  const assignmentsQ = useQuery({
    queryKey: ["assignments", trialId],
    queryFn: () => api.listAssignments(trialId),
  });
  const [selectedSite, setSelectedSite] = useState<string>("");
  // The Add-site row defaults are derived from the study-level targets (Basics
  // step). On the first site, default = full study target; subsequent sites
  // default to whatever is still unallocated so the totals stay linked.
  const studyRand = trialQ.data?.enrollment_target ?? 0;
  const studyScreen = trialQ.data?.screening_target ?? 0;
  const assigned = assignmentsQ.data ?? [];
  const sumAssignedRand = assigned.reduce(
    (s, a) => s + a.per_site_enrollment_target,
    0,
  );
  const sumAssignedScreen = assigned.reduce(
    (s, a) => s + a.per_site_screening_target,
    0,
  );
  const remainingRand = Math.max(0, studyRand - sumAssignedRand);
  const remainingScreen = Math.max(0, studyScreen - sumAssignedScreen);
  const [rand, setRand] = useState<number>(0);
  const [screen, setScreen] = useState<number>(0);
  const [randTouched, setRandTouched] = useState(false);
  const [screenTouched, setScreenTouched] = useState(false);
  // Reflect remaining-to-allocate into the inputs until the user types into
  // them; once touched, leave their entry alone.
  useEffect(() => {
    if (!randTouched) setRand(remainingRand);
  }, [remainingRand, randTouched]);
  useEffect(() => {
    if (!screenTouched) setScreen(remainingScreen);
  }, [remainingScreen, screenTouched]);

  const [error, setError] = useState<string | null>(null);
  // Mismatch reconciliation modal — fired on Continue when site totals don't
  // match the study target.
  const [mismatch, setMismatch] = useState<{
    siteTotalRand: number;
    siteTotalScreen: number;
  } | null>(null);

  const qc = useQueryClient();
  const assign = useMutation({
    mutationFn: async () => {
      if (!selectedSite) throw new Error("pick a site");
      return await api.assignSiteToTrial(trialId, {
        site_id: selectedSite,
        per_site_enrollment_target: rand,
        per_site_screening_target: screen,
      });
    },
    onSuccess: () => {
      setSelectedSite("");
      setRandTouched(false);
      setScreenTouched(false);
      setError(null);
      qc.invalidateQueries({ queryKey: ["assignments", trialId] });
    },
    onError: () => setError("Failed to assign site."),
  });
  const patchTargets = useMutation({
    mutationFn: async (patch: {
      enrollment_target: number;
      screening_target: number;
    }) => api.patchTrial(trialId, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trial", trialId] });
      qc.invalidateQueries({ queryKey: ["trials"] });
    },
  });

  const assignedIds = useMemo(
    () => new Set(assigned.map((a) => a.site_id)),
    [assigned],
  );
  const available = (sitesQ.data ?? []).filter((s) => !assignedIds.has(s.id));
  const sitesById = new Map((sitesQ.data ?? []).map((s) => [s.id, s]));

  function onContinueClick() {
    const rTot = sumAssignedRand;
    const sTot = sumAssignedScreen;
    if (rTot !== studyRand || sTot !== studyScreen) {
      setMismatch({ siteTotalRand: rTot, siteTotalScreen: sTot });
      return;
    }
    onDone();
  }

  async function acceptSiteTotalsAsStudy() {
    if (!mismatch) return;
    await patchTargets.mutateAsync({
      enrollment_target: mismatch.siteTotalRand,
      screening_target: mismatch.siteTotalScreen,
    });
    setMismatch(null);
    onDone();
  }

  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-base font-semibold">Sites &amp; targets</h2>
      <p className="mb-3 text-sm text-slate-500">
        Assign sites and set their per-site randomization/screening targets.
        Site totals must sum to the study-level targets set in Basics
        ({studyRand} randomized / {studyScreen} screened).
      </p>

      <div className="mb-4 rounded border border-slate-200 bg-slate-50 p-3">
        <h3 className="mb-2 text-sm font-medium">Add site</h3>
        <div className="grid gap-2 md:grid-cols-4">
          <select
            value={selectedSite}
            onChange={(e) => setSelectedSite(e.target.value)}
            className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
            data-testid="sites-picker"
          >
            <option value="">Select a site…</option>
            {available.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <label className="text-sm">
            Rand target
            <input
              type="number"
              min={0}
              value={rand}
              onChange={(e) => {
                setRand(Number(e.target.value));
                setRandTouched(true);
              }}
              className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1.5"
              data-testid="sites-rand-input"
            />
          </label>
          <label className="text-sm">
            Screen target
            <input
              type="number"
              min={0}
              value={screen}
              onChange={(e) => {
                setScreen(Number(e.target.value));
                setScreenTouched(true);
              }}
              className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1.5"
              data-testid="sites-screen-input"
            />
          </label>
          <button
            type="button"
            onClick={() => assign.mutate()}
            disabled={!selectedSite || assign.isPending}
            className="self-end rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            data-testid="sites-assign"
          >
            {assign.isPending ? "Adding…" : "Add"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Defaults to the remaining unallocated targets ({remainingRand} rand /{" "}
          {remainingScreen} screen). Edit before Add to override.
        </p>
        {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      </div>

      <h3 className="mb-2 text-sm font-medium">
        Assigned ({assigned.length})
      </h3>
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
          <tr>
            <th className="px-3 py-2">Site</th>
            <th className="px-3 py-2 text-right">Rand</th>
            <th className="px-3 py-2 text-right">Screen</th>
          </tr>
        </thead>
        <tbody>
          {assigned.map((a) => {
            const s = sitesById.get(a.site_id);
            return (
              <tr key={a.id} className="border-t border-slate-100">
                <td className="px-3 py-1.5">{s?.name ?? a.site_id.slice(0, 6)}</td>
                <td className="px-3 py-1.5 text-right">
                  {a.per_site_enrollment_target}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {a.per_site_screening_target}
                </td>
              </tr>
            );
          })}
          {assigned.length === 0 && (
            <tr>
              <td colSpan={3} className="py-4 text-center text-slate-500">
                No sites assigned yet.
              </td>
            </tr>
          )}
          {assigned.length > 0 && (
            <tr className="border-t border-slate-300 bg-slate-50 font-medium">
              <td className="px-3 py-1.5">Total</td>
              <td
                className={`px-3 py-1.5 text-right ${
                  sumAssignedRand === studyRand
                    ? "text-emerald-700"
                    : "text-amber-700"
                }`}
                data-testid="sites-total-rand"
              >
                {sumAssignedRand} / {studyRand}
              </td>
              <td
                className={`px-3 py-1.5 text-right ${
                  sumAssignedScreen === studyScreen
                    ? "text-emerald-700"
                    : "text-amber-700"
                }`}
                data-testid="sites-total-screen"
              >
                {sumAssignedScreen} / {studyScreen}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={onContinueClick}
          disabled={assigned.length === 0}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          data-testid="sites-continue"
        >
          Continue →
        </button>
      </div>

      {mismatch && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4"
          data-testid="sites-mismatch-dialog"
        >
          <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-lg">
            <h3 className="text-base font-semibold text-slate-900">
              Site totals don&rsquo;t match the study targets
            </h3>
            <p className="mt-2 text-sm text-slate-600">
              Your assigned sites sum to{" "}
              <strong>{mismatch.siteTotalRand}</strong> randomized /{" "}
              <strong>{mismatch.siteTotalScreen}</strong> screened, but Basics is
              set to <strong>{studyRand}</strong> /{" "}
              <strong>{studyScreen}</strong>. Pick one to reconcile before
              continuing.
            </p>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setMismatch(null)}
                className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                data-testid="sites-mismatch-fix"
              >
                Back — fix site rows
              </button>
              <button
                type="button"
                onClick={acceptSiteTotalsAsStudy}
                disabled={patchTargets.isPending}
                className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
                data-testid="sites-mismatch-update-study"
              >
                {patchTargets.isPending
                  ? "Updating…"
                  : `Update study to ${mismatch.siteTotalRand} / ${mismatch.siteTotalScreen}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ============================================================================
// Step 4: Visit pricing — set USD price per visit
// ============================================================================

function PricingStep({ trialId, onDone }: { trialId: string; onDone: () => void }) {
  const armsQ = useQuery({
    queryKey: ["arms", trialId],
    queryFn: () => api.listArms(trialId),
  });
  const armId = armsQ.data?.[0]?.id ?? null;
  const visitsQ = useQuery({
    queryKey: ["visits", armId],
    queryFn: () => api.listVisits(armId!),
    enabled: !!armId,
  });

  const [prices, setPrices] = useState<Record<string, number | null>>({});
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (visitsQ.data) {
      setPrices(
        Object.fromEntries(visitsQ.data.map((v) => [v.id, v.price ?? null])),
      );
      setDirty(false);
    }
  }, [visitsQ.data]);

  useUnsavedChangesGuard({ dirty });

  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: async () => {
      if (!armId) throw new Error("no arm");
      for (const v of visitsQ.data ?? []) {
        const newPrice = prices[v.id] ?? null;
        if (newPrice !== (v.price ?? null)) {
          await api.patchVisit(armId, v.id, { price: newPrice });
        }
      }
    },
    onSuccess: () => {
      setDirty(false);
      setError(null);
      qc.invalidateQueries({ queryKey: ["visits", armId] });
    },
    onError: () => setError("Failed to save prices."),
  });

  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-base font-semibold">Visit pricing</h2>
      <p className="mb-3 text-sm text-slate-500">
        Set the USD price per visit. Trials without pricing are "volume-ready" but
        not "revenue-ready" — both still activate.
      </p>
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
          <tr>
            <th className="px-3 py-2">Visit</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2 text-right">Price (USD)</th>
          </tr>
        </thead>
        <tbody>
          {(visitsQ.data ?? []).map((v) => (
            <tr key={v.id} className="border-t border-slate-100">
              <td className="px-3 py-1.5">{v.name}</td>
              <td className="px-3 py-1.5 text-slate-500">{v.visit_type}</td>
              <td className="px-3 py-1.5 text-right">
                <input
                  type="number"
                  min={0}
                  step={50}
                  value={prices[v.id] ?? ""}
                  onChange={(e) => {
                    const n = e.target.value === "" ? null : Number(e.target.value);
                    setPrices((p) => ({ ...p, [v.id]: n }));
                    setDirty(true);
                  }}
                  className="w-28 rounded border border-slate-300 px-2 py-1 text-right"
                  data-testid={`price-${v.id}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={!dirty || save.isPending}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
          data-testid="pricing-save"
        >
          {save.isPending ? "Saving…" : dirty ? "Save" : "Saved"}
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white"
          data-testid="pricing-continue"
        >
          Continue →
        </button>
      </div>
    </section>
  );
}

// ============================================================================
// Step 5: Attrition — pick the curve
// ============================================================================

function AttritionStep({ trialId, onDone }: { trialId: string; onDone: () => void }) {
  const curvesQ = useQuery({
    queryKey: ["attrition-curves"],
    queryFn: api.listAttritionCurves,
  });
  const trialsQ = useQuery({
    queryKey: ["trial-current", trialId],
    queryFn: async () => {
      const all = await api.listTrials();
      return all.find((t) => t.id === trialId) ?? null;
    },
  });

  const [selected, setSelected] = useState<string>("");
  useEffect(() => {
    if (trialsQ.data?.attrition_curve_id) {
      setSelected(trialsQ.data.attrition_curve_id);
    }
  }, [trialsQ.data]);

  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: async () => {
      await api.patchTrial(trialId, { attrition_curve_id: selected } as never);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trials"] });
      onDone();
    },
  });

  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-base font-semibold">Attrition</h2>
      <p className="mb-3 text-sm text-slate-500">
        Pick the dropout curve for this trial. Defaults to Standard (20%).
      </p>
      <div className="space-y-2">
        {(curvesQ.data ?? []).map((c) => (
          <label
            key={c.id}
            className={`flex cursor-pointer items-center gap-3 rounded border p-3 ${
              selected === c.id
                ? "border-slate-900 bg-slate-50"
                : "border-slate-200"
            }`}
          >
            <input
              type="radio"
              name="attrition"
              value={c.id}
              checked={selected === c.id}
              onChange={() => setSelected(c.id)}
            />
            <div>
              <p className="font-medium">
                {c.name}{" "}
                {c.is_preset && (
                  <span className="ml-1 text-xs text-slate-500">(preset)</span>
                )}
              </p>
              <p className="text-sm text-slate-500">
                Total dropout {(c.total_dropout_pct * 100).toFixed(0)}%, linear back-loaded
              </p>
            </div>
          </label>
        ))}
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={!selected || save.isPending}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          data-testid="attrition-continue"
        >
          Save & continue →
        </button>
      </div>
    </section>
  );
}

// ============================================================================
// Step 6: Activate
// ============================================================================

function ActivateStep({ trialId }: { trialId: string }) {
  const navigate = useNavigate();
  const [failures, setFailures] = useState<
    Array<{ reason: string; detail: string }> | null
  >(null);
  // null = not yet transitioned; otherwise which status we landed in.
  const [outcome, setOutcome] = useState<"active" | "planned" | null>(null);

  const onError = (err: unknown) => {
    if (err instanceof ApiError && err.status === 422) {
      const body = err.body as
        | { detail?: { failures?: Array<{ reason: string; detail: string }> } }
        | null;
      setFailures(body?.detail?.failures ?? []);
    } else {
      setFailures([{ reason: "unknown_error", detail: String(err) }]);
    }
  };

  const activate = useMutation({
    mutationFn: async () => await api.activateTrial(trialId),
    onSuccess: () => {
      setFailures(null);
      setOutcome("active");
    },
    onError,
  });

  // Same readiness gate as activation, but parks the trial as future pipeline.
  const plan = useMutation({
    mutationFn: async () => await api.planTrial(trialId),
    onSuccess: () => {
      setFailures(null);
      setOutcome("planned");
    },
    onError,
  });

  const busy = activate.isPending || plan.isPending;

  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-base font-semibold">Activate or plan</h2>
      <p className="mb-3 text-sm text-slate-500">
        Both require: a randomization visit, at least one assigned site, and an
        attrition curve (pricing not required). Choose <strong>Activate</strong>{" "}
        if the trial is running now, or <strong>Mark as planned</strong> if it's
        configured but starts in the future — planned trials are forecast as a
        separate pipeline (PRD §6.9).
      </p>
      {outcome ? (
        <div data-testid="activate-success" className="rounded border border-emerald-200 bg-emerald-50 p-3">
          <p className="font-medium text-emerald-900">
            {outcome === "active" ? "✓ Trial activated." : "✓ Trial marked as planned."}
          </p>
          <p className="mt-1 text-sm text-emerald-900">
            Next: enter your per-site weekly screening + randomization
            projections so the forecast can produce demand curves.
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => navigate("/projections")}
              className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white"
              data-testid="activate-enter-projections"
            >
              Enter projections →
            </button>
            <button
              type="button"
              onClick={() => navigate(`/trials/${trialId}`)}
              className="rounded border border-slate-300 px-3 py-1.5 text-sm"
              data-testid="activate-view-trial"
            >
              View trial
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => activate.mutate()}
            disabled={busy}
            className="rounded bg-slate-900 px-4 py-1.5 text-sm text-white disabled:opacity-40"
            data-testid="activate-button"
          >
            {activate.isPending ? "Activating…" : "Activate trial"}
          </button>
          <button
            type="button"
            onClick={() => plan.mutate()}
            disabled={busy}
            className="rounded border border-slate-300 px-4 py-1.5 text-sm text-slate-700 disabled:opacity-40"
            data-testid="plan-button"
          >
            {plan.isPending ? "Marking…" : "Mark as planned"}
          </button>
        </div>
      )}
      {failures && failures.length > 0 && (
        <div
          className="mt-4 rounded border border-amber-200 bg-amber-50 p-3"
          data-testid="activate-failures"
        >
          <p className="font-medium text-amber-900">
            Activation blocked — resolve these first:
          </p>
          <ul className="mt-2 list-disc pl-5 text-sm text-amber-900">
            {failures.map((f) => (
              <li key={f.reason}>
                <strong>{f.reason}:</strong> {f.detail}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

// ============================================================================
// Shared
// ============================================================================

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-0.5 block text-xs font-medium text-slate-600">
        {label}
      </span>
      {children}
    </label>
  );
}
