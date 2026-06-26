# v2 — What-If Simulation (design framework)

> Status: **design discussion, pre-PRD.** Not yet built. This is the working
> framework agreed for the v2 headline feature; the next gate is a `docs/prd.md`
> v2 section + sign-off before any code (project rule: PRD is source of truth).

## Decision context

- **v2 north star:** What-if simulation. It's the PRD's designated v2 headline,
  the engine was explicitly built to accept hypothetical commitments, and the
  Planned-status + ForecastScope work (post-v1) is a direct stepping stone.
- **Commercial stage:** pre-customer / demo-driven. So we optimize for the
  *closing demo* (differentiation), not operational hardening.
- **Deferred for now:** recruitment funnel and CTMS integration (new domain /
  multi-month, not demo-critical). SSO slotted in only if a deal needs it.

## The demo this is building toward

1. Exec opens the network grid: today's active forecast — some sites green
   (headroom), some red (at risk).
2. *"We're weighing Sponsor Z's Phase II — ~200 patients, starts Q3."* They spin
   up a **what-if scenario**: candidate sites, a visit schedule, an enrollment
   ramp, a start date.
3. The grid **overlays the impact instantly** — Site A absorbs it (stays green),
   Site B tips into red. No real data touched.
4. *(Cost/margin fast-follow)* The same view shows the **revenue / margin** the
   scenario adds → *"that's $X of profitable volume, and only Site B needs
   attention."*

This makes the README mission literal — "decide where there's room to sell and
where capacity is at risk."

## Mental model: a scenario is baseline + overlay

A scenario never edits reality:

```
scenario forecast = compute_forecast( baseline_commitments + overlay_commitments )
                                       └── real active ──┘   └── hypothetical ──┘
```

Everything downstream of `compute_forecast` already works (capacity, utilization
bands, revenue, ranges). The entire job of the what-if module is to **synthesize
the overlay commitments** and hand the union to the unchanged engine.

## Data flow (reuses the existing seam)

The one seam is `build_commitments` in `forecast_adapter.py`. Add a sibling:

```python
build_scenario_commitments(db, org_id, scenario, baseline_scope=ACTIVE):
    baseline = build_commitments(db, org_id, statuses=scope_statuses(baseline_scope))  # real
    overlay  = synthesize_overlay(db, org_id, scenario)                                # hypothetical
    return baseline, overlay   # caller picks baseline / overlay / both
```

`synthesize_overlay` builds the same `Commitment` tuples the engine already eats
— `(Site, Trial, Arm, Visits, AttritionCurve, EnrollmentWeeks, durations)` —
except the Trial / Visits / weeks come from the scenario spec instead of DB rows.
**The engine and the core tables stay untouched** (golden rule #2; same
discipline as the ForecastScope work).

Capacity is the elegant part: `capacity_hours = rooms × operating_days ×
hours_per_day` is independent of trials. Dropping an overlay trial onto a site
raises demand, capacity stays → utilization climbs → the cell crosses amber/red
on its own. The "where's room / where tips over" answer falls out of the existing
math for free.

## What a hypothetical trial needs

To synthesize one overlay trial:

- **Schedule (SoA):** reuse an existing trial's visits as a **template** (fast,
  realistic) — pick "Sponsor Y's Phase II schedule" from a dropdown.
- **Attrition:** a preset (Standard) or an existing curve.
- **Target sites:** a multi-select of real sites.
- **Enrollment:** a *ramp spec* the builder expands into weekly numbers.

Example ramp expansion (a small **pure function worth golden-mastering**):

> "200 randomized / 250 screened, start 2026-09-07, 40-week linear ramp"
> → per-week `proj_screened` / `proj_randomized` across those Mondays.

Distribute **both** the randomized and screened targets (the same dual-target
shape real trials carry), so modeling decision #1 — screening driven by the
`screened` projection directly — is preserved. Ramp shapes: linear or S-curve to
steady-state.

## API (mirrors the forecast surface)

- `POST/GET/PATCH/DELETE /scenarios` — CRUD, org-scoped + RLS, like any entity.
- `GET /scenarios/{id}/forecast?from=&to=&view=baseline|scenario|combined` —
  returns the existing `ForecastCellOut[]`. `view` is the what-if analog of
  `scope`. The UI diffs baseline vs combined to highlight what moved — no new
  cell shape.

## UI

The network grid gains a **Baseline / Scenario / Combined** toggle (extends the
existing `ScopeToggle`), plus **delta highlighting** — cells pushed
green→amber→red by the scenario get a marker. KPI strip: "sites tipped into risk:
N", "added demand hours", and (Phase D) "added revenue / margin."

## Design forks (recommended defaults)

| Fork | Options | Recommended default |
|---|---|---|
| **Where the hypothetical lives** | (a) JSON overlay on the `Scenario` row · (b) parallel `scenario_*` tables · (c) flag rows in real tables with `scenario_id` | **(a) JSON overlay** — cleanest isolation (can't leak into real forecasts), fastest to demo. Grow to (b) only if scenarios need rich editing. **Avoid (c)** — forces every query/RLS path to be scenario-aware. |
| **SoA source** | template from existing trial · inline authoring · both | **Template** for v2.0; inline later |
| **Enrollment input** | ramp-spec auto-expanded · explicit weekly grid · both | **Ramp-spec** (demo speed); reuse the spreadsheet grid later |
| **What "moves" exist** | add hypothetical trial · also add-existing-to-more-sites / remove / resize | **Add-trial only** for v2.0 (the headline); keep the model general |
| **Baseline layer** | active only · active+planned selectable | **Active default, allow active+planned** — a three-layer story (committed → pipeline → what-if) is a strong demo |

**Keystone decision:** the first row (JSON overlay vs scenario tables) — it
determines whether `synthesize_overlay` reads a blob or a parallel schema, and
it's the hardest to change later.

## Proposed phased build (same gated discipline as v1, PRD-first)

1. **v2 PRD section** — Scenario model, what-if forecast semantics, demo flow.
   *Sign-off before code.* Locks the forks above.
2. **Phase A — Scenario engine adapter (pure, golden-mastered).** Generalize
   `build_commitments` to merge baseline + hypothetical; golden-master a scenario
   fixture and the `ramp_to_weeks` expansion. Riskiest/highest-value → first,
   mirroring v1's "engine first."
3. **Phase B — Scenario model + API.** CRUD (RLS), hypothetical
   trial/sites/ramp inputs, forecast endpoint returning baseline / scenario /
   combined.
4. **Phase C — What-if UI.** Scenario builder + grid overlay with delta
   highlighting, extending `ScopeToggle`.
5. **Phase D — Cost & margin fast-follow.** Light up `Visit.cost` / price in the
   scenario view → the "profitable room" headline that completes the closing demo.

## Open question before PRD

Lock the recommended-default column as-is, or push on a fork first (especially
the storage keystone)?
