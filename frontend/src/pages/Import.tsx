/**
 * Bulk CSV import (post-Phase-6).
 *
 * Three tabs — Sites, Trials, Projections — sharing the same workflow:
 *   1. Download template
 *   2. Pick a file
 *   3. Preview (server-side validation, no writes)
 *   4. Commit (re-validated in one DB transaction; all-or-nothing)
 *
 * Role-gated to org_admin (matches AdminSettings posture).
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError, api, type Me } from "../api";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type Kind = "sites" | "trials" | "projections";

const KIND_LABEL: Record<Kind, string> = {
  sites: "Sites",
  trials: "Trials",
  projections: "Projections",
};

const KIND_HINT: Record<Kind, string> = {
  sites:
    "One row per site. operating_weekdays accepts \"Mon Tue Wed Thu Fri\" or \"0,1,2,3,4\".",
  trials:
    "One row per (trial, site) assignment. Trial-level fields can be left blank on rows 2+ for the same trial (inherit). Sum of per-site targets must equal the study targets. Imports as draft. The XLSX template's Reference sheet lists your existing site names so you can paste them in exactly.",
  projections:
    "One row per (site, trial, arm, week). week_start must be a Monday. arm_name left blank → \"Default Arm\". Re-uploading an existing week overwrites the projection (actuals untouched). The XLSX template's Reference sheet lists your existing trial + arm names.",
};

export default function Import({ me }: { me: Me }) {
  useDocumentTitle("Import");

  if (me.role !== "org_admin") {
    return (
      <div className="mx-auto mt-12 max-w-2xl p-6">
        <h1 className="text-2xl font-semibold">Bulk import</h1>
        <p className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Only Org Admins can import data.
        </p>
      </div>
    );
  }

  const [kind, setKind] = useState<Kind>("sites");

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-6">
      <nav className="text-sm text-slate-500" aria-label="Breadcrumb">
        <Link to="/" className="hover:underline">
          Network
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">Bulk import</span>
      </nav>

      <header>
        <h1 className="text-2xl font-semibold">Bulk import</h1>
        <p className="mt-1 text-sm text-slate-500">
          Download a template, fill it in, preview, then commit. Errors anywhere
          in the file block the whole upload — nothing is written until the
          preview is clean.
        </p>
      </header>

      <div
        className="inline-flex rounded border border-slate-300"
        role="tablist"
        data-testid="import-tabs"
      >
        {(["sites", "trials", "projections"] as Kind[]).map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={kind === k}
            onClick={() => setKind(k)}
            className={`px-3 py-1.5 text-sm ${
              kind === k
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-700"
            } ${k !== "sites" ? "border-l border-slate-300" : ""}`}
            data-testid={`import-tab-${k}`}
          >
            {KIND_LABEL[k]}
          </button>
        ))}
      </div>

      <ImportPanel kind={kind} key={kind} />
    </div>
  );
}

function ImportPanel({ kind }: { kind: Kind }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{
    ok: boolean;
    actions: string[];
    errors: Array<{ row: number; message: string }>;
  } | null>(null);
  const [status, setStatus] = useState<
    "idle" | "previewing" | "committing" | "committed" | "error"
  >("idle");
  const [committedActions, setCommittedActions] = useState<string[]>([]);
  const [errorText, setErrorText] = useState<string | null>(null);

  async function runPreview() {
    if (!file) return;
    setStatus("previewing");
    setErrorText(null);
    try {
      const r = await api.previewImport(kind, file);
      setPreview(r);
      setStatus("idle");
    } catch (err) {
      setStatus("error");
      setErrorText(err instanceof Error ? err.message : "preview failed");
    }
  }

  async function runCommit() {
    if (!file) return;
    setStatus("committing");
    setErrorText(null);
    try {
      const r = await api.commitImport(kind, file);
      setCommittedActions(r.actions);
      setStatus("committed");
      // Invalidate every cache that the committed kind could affect — these
      // are cheap, no point being clever.
      qc.invalidateQueries({ queryKey: ["sites"] });
      qc.invalidateQueries({ queryKey: ["trials"] });
      qc.invalidateQueries({ queryKey: ["trials-active"] });
      qc.invalidateQueries({ queryKey: ["forecast-network"] });
    } catch (err) {
      setStatus("error");
      if (err instanceof ApiError && err.status === 422) {
        const body = err.body as {
          detail?: { errors?: Array<{ row: number; message: string }> };
        } | null;
        const errs = body?.detail?.errors ?? [];
        setPreview({ ok: false, actions: [], errors: errs });
        setErrorText("Validation failed — see errors below.");
      } else {
        setErrorText(err instanceof Error ? err.message : "commit failed");
      }
    }
  }

  function reset() {
    setFile(null);
    setPreview(null);
    setCommittedActions([]);
    setStatus("idle");
    setErrorText(null);
  }

  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-600">{KIND_HINT[kind]}</p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <a
          href={api.importTemplateUrl(kind, "xlsx")}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm"
          data-testid={`import-${kind}-download-template`}
        >
          Download {KIND_LABEL[kind]} template (.xlsx)
        </a>
        <a
          href={api.importTemplateUrl(kind, "csv")}
          className="text-xs text-slate-500 underline"
          data-testid={`import-${kind}-download-csv`}
        >
          (or CSV)
        </a>
        <label className="text-sm text-slate-700">
          <span className="mr-2">File:</span>
          <input
            type="file"
            accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setPreview(null);
              setCommittedActions([]);
              setStatus("idle");
              setErrorText(null);
            }}
            data-testid={`import-${kind}-file`}
          />
        </label>
        <button
          type="button"
          onClick={runPreview}
          disabled={!file || status === "previewing" || status === "committing"}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
          data-testid={`import-${kind}-preview`}
        >
          {status === "previewing" ? "Validating…" : "Preview"}
        </button>
        <button
          type="button"
          onClick={runCommit}
          disabled={
            !file ||
            !preview ||
            !preview.ok ||
            status === "committing" ||
            status === "committed"
          }
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          data-testid={`import-${kind}-commit`}
        >
          {status === "committing" ? "Importing…" : "Commit"}
        </button>
      </div>

      {errorText && (
        <p
          className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800"
          data-testid={`import-${kind}-error`}
        >
          {errorText}
        </p>
      )}

      {status === "committed" && (
        <div
          className="mt-4 rounded border border-emerald-200 bg-emerald-50 p-3"
          data-testid={`import-${kind}-success`}
        >
          <p className="font-medium text-emerald-900">
            ✓ Import complete — {committedActions.length} change
            {committedActions.length === 1 ? "" : "s"} written.
          </p>
          <ul className="mt-2 max-h-48 list-disc overflow-y-auto pl-5 text-sm text-emerald-900">
            {committedActions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
          <button
            type="button"
            onClick={reset}
            className="mt-3 rounded border border-emerald-300 px-3 py-1 text-xs text-emerald-900"
          >
            Import another file
          </button>
        </div>
      )}

      {preview && status !== "committed" && (
        <div className="mt-4 space-y-3">
          {preview.errors.length > 0 && (
            <div
              className="rounded border border-red-200 bg-red-50 p-3"
              data-testid={`import-${kind}-errors`}
            >
              <p className="font-medium text-red-900">
                {preview.errors.length} error
                {preview.errors.length === 1 ? "" : "s"} — fix and re-preview.
              </p>
              <table className="mt-2 w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-red-800">
                  <tr>
                    <th className="py-1 pr-3">Row</th>
                    <th className="py-1">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.errors.map((e, i) => (
                    <tr key={i} className="border-t border-red-200">
                      <td className="py-1 pr-3 align-top font-mono text-red-900">
                        {e.row === 0 ? "—" : e.row}
                      </td>
                      <td className="py-1 text-red-900">{e.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {preview.actions.length > 0 && (
            <div
              className={`rounded border p-3 ${
                preview.ok
                  ? "border-emerald-200 bg-emerald-50"
                  : "border-slate-200 bg-slate-50"
              }`}
            >
              <p
                className={`font-medium ${
                  preview.ok ? "text-emerald-900" : "text-slate-700"
                }`}
              >
                {preview.ok
                  ? `Looks good — ${preview.actions.length} change${preview.actions.length === 1 ? "" : "s"} ready to commit.`
                  : `${preview.actions.length} parseable row${preview.actions.length === 1 ? "" : "s"} (not committable until errors above are fixed).`}
              </p>
              <ul className="mt-2 max-h-64 list-disc overflow-y-auto pl-5 text-sm text-slate-800">
                {preview.actions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
