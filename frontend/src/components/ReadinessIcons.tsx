/**
 * Activation-readiness icons for a draft/planned study (Studies dashboard).
 *
 * Three requirement chips — SoA, Site, Curve — each green (satisfied) or amber
 * (missing) with a tooltip explaining what's wrong. The failure reasons come
 * straight from the activation gate (GET /trials/readiness), so the chips never
 * drift from what activation actually checks.
 */

type Failure = { reason: string; detail: string };

const REQUIREMENTS: {
  key: string;
  label: string;
  /** Activation failure reasons that mean this requirement is unmet. */
  reasons: string[];
  okTitle: string;
}[] = [
  {
    key: "soa",
    label: "SoA",
    reasons: ["no_arms", "no_visits", "no_randomization_visit"],
    okTitle: "Schedule of Activities ready (has a randomization visit)",
  },
  {
    key: "site",
    label: "Site",
    reasons: ["no_sites"],
    okTitle: "At least one site assigned",
  },
  {
    key: "curve",
    label: "Curve",
    reasons: ["no_attrition_curve"],
    okTitle: "Attrition curve assigned",
  },
];

export function ReadinessIcons({ failures }: { failures: Failure[] }) {
  const byReason = new Map(failures.map((f) => [f.reason, f.detail]));
  return (
    <div className="flex items-center justify-end gap-1.5 no-print">
      {REQUIREMENTS.map((req) => {
        const missingReason = req.reasons.find((r) => byReason.has(r));
        const missing = missingReason !== undefined;
        const title = missing ? byReason.get(missingReason)! : req.okTitle;
        return (
          <span
            key={req.key}
            title={title}
            aria-label={`${req.label}: ${missing ? "missing" : "ready"}`}
            data-testid={`readiness-${req.key}-${missing ? "missing" : "ok"}`}
            className={
              "inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-xs " +
              (missing
                ? "bg-amber-100 text-amber-800"
                : "bg-emerald-100 text-emerald-800")
            }
          >
            <span aria-hidden>{missing ? "⚠" : "✓"}</span>
            {req.label}
          </span>
        );
      })}
    </div>
  );
}
