# Audit & Improvement Log — Session 6

**Goal:** Identify improvements to move the app toward "leading UK financial
planning tool for net worth and retirement". Preserve all current content;
tidy is fine.

**Started from:** v2.4 (post Session 5 audit).

---

## Methodology

1. Walk through the live app journey from a real user's perspective (cold start, no data).
2. Generate fresh PDFs for representative personas and inspect visually.
3. Compare the feature set against what a "leading" planning tool offers
   (drawdown modelling, tax wrappers, state pension forecast, sequence-of-returns
   risk, etc.).
4. Categorise findings by impact × effort; ship the highest-value items.

---

## Findings

### A. User journey gaps (cold start — no personal data yet)

- **A1.** No clear call-to-action — landing shows the benchmark chart but the
  big "what to do next" is buried in the sidebar. A new visitor has to scroll
  the long sidebar to find the upload widget.
- **A2.** Sample / demo data not offered. Could populate a fake persona to let
  users explore before entering their own figures.

### B. Sidebar information architecture

- **B1.** Sidebar is long: 10+ display toggles, two personal data sections,
  wealth composition expander, goal calculator (with 4 sub-tools nested),
  benchmark download. Mixing display options with personal data and
  calculators.
- **B2.** Display toggles (log scale, P10/P90, milestones, smooth, asset class,
  annotations, colourblind) could be folded into a single "Display options"
  expander to declutter.
- **B3.** Goal calculator combines four distinct things (target NW, FIRE, pension
  pot, savings rate) into one expander — confusing because the dependencies
  between them aren't visible.

### C. Retirement planning — the biggest gap vs a "leading" tool

- **C1.** **No drawdown / decumulation modelling.** Currently only FIRE = 25×
  (which is the 4% rule) but no actual simulation of "if I retire at 60 with
  £X and withdraw £Y/yr, when does my pot run out?". This is the central
  question a retirement planning tool answers.
- **C2.** **No retirement income view.** A user can input state pension and
  target pension income, but the app never shows "your projected total annual
  income at retirement = state pension £X + DB pension £Y + drawdown £Z".
- **C3.** **No sequence-of-returns illustration.** Order of returns matters
  during decumulation — a stochastic or "bad early years" scenario would be
  genuinely useful.
- **C4.** **Inflation assumption is implicit.** "Real terms 2026 £" is a
  toggle but during what-if projection it's not clear whether the projected
  values are real or nominal. Same for FIRE.
- **C5.** **No tax wrapper guidance.** UK has ISA (£20k/yr), Pension AA
  (£60k/yr), LISA (£4k/yr), and various tapers. Tracking utilisation is a
  core planning function.

### D. Calculation quality

- **D1.** Pension pot estimator uses annuity rate `0.05 + (age-65) × 0.002` —
  conservative. Recent UK gilt-linked annuity rates at 65 have been closer to
  6.5–7% in 2024/25.
- **D2.** State pension default is £11,500/yr (2024/25). 2025/26 was £11,973;
  2026/27 will be ~£12.4k. Should update default to current.
- **D3.** Sustainable spending shown as `nw / 25 / 52` weekly — implies 4% SWR
  but doesn't account for tax. Real after-tax sustainable spend is lower
  for amounts above the Personal Allowance.

### E. Polish / consistency

- **E1.** Methodology mentions "Region filter is planned for v2" — stale, we're
  on v2.4.
- **E2.** Caption "Indicative only" repeated many times — slight variation
  would feel more thoughtful.
- **E3.** Some expander captions use bold markdown, others don't — could be consistent.
- **E4.** No "last updated" or "version" visible to a casual viewer except the
  small footer.

### F. PDF report

- **F1.** Already strong post-Session 5. One small thing: the "Goals" page
  doesn't show the retirement income summary that would tie it together.
- **F2.** PDF doesn't include a drawdown chart (if we add C1).

### G. Already strong areas (preserve)

- Benchmark visualisation
- PCHIP interpolation
- Multi-page PDF report
- IHT calculator
- Asset class breakdown
- Percentile trajectory
- Year-on-year gains chart
- Share-link encoding
- Data quality score
- Methodology transparency

---

## Implementation plan (this session)

Ordered by impact × effort.

| # | Item | Effort | Impact |
|---|---|---|---|
| 1 | Drawdown / decumulation simulator | Medium | **High** — closes biggest gap |
| 2 | Retirement income summary (state + private + draw) | Low | **High** — answers the "what will I live on?" question |
| 3 | Update state pension default + annuity rate | Trivial | Med |
| 4 | Sidebar reorganisation (Display options expander) | Low | Med |
| 5 | Empty-state landing tips | Low | Med |
| 6 | Inflation note clearer on what-if and FIRE | Trivial | Med |
| 7 | Update methodology stale notes | Trivial | Low |
| 8 | Add drawdown chart + summary to PDF | Low (after #1) | Med |

---

## Implemented this session (v2.5)

### New: Retirement income forecast (in-app + PDF)
- New expander in the main flow that brings together the user's projected NW
  at retirement age, their pension share, state pension, and the assumed real
  return, then shows estimated annual income from three sources side-by-side:
  - Pension annuity (using gilt-linked rate ~6.5% at 65)
  - 4% safe-withdrawal drawdown from non-pension wealth
  - State pension (from age 67+)
- Compares the total against the user's target pension income with success /
  warning banner.
- New page in the PDF report with a full income breakdown table.

### New: Retirement drawdown — pot longevity simulator
- New expander that simulates spending down a retirement pot year-by-year.
- Headline metrics: years covered, depletion age, life-expectancy comparison,
  implied withdrawal rate.
- Pot-balance chart with life-expectancy and depletion markers.
- Sensitivity table showing depletion age at real returns from 1% to 6%.
- Optional state pension overlay (reduces drawdown need from age 67).
- Verdict banner colour-coded by whether the pot covers life expectancy.
- Documents sequence-of-returns risk and how to stress-test.

### Polish & quick wins
- **State pension default** updated: £11,500 (2024/25) → £12,400 (2026/27 estimate).
- **Annuity rate assumption** updated from 5% to 6.5% at age 65 to reflect 2024/25
  UK gilt-linked annuity rates. Affects pension pot estimator and retirement income.
- **Sidebar tidy**: log scale, P10/P90, milestones, smooth trajectory, asset class,
  annotations, colourblind palette toggles all moved into a "Display options"
  expander. The age range slider stays prominent.
- **Empty-state guidance**: friendly "Add your net worth history to get started"
  banner shown on cold start, pointing the user at the sidebar.
- **Methodology**: added sections describing the retirement income forecast and
  drawdown simulator. Removed stale "Region filter is planned for v2" line.
- **Version**: bumped APP_VERSION to v2.5.

---

## Not done this session (queued for the backlog)

- **Tax wrapper tracking** (ISA / Pension AA / LISA utilisation) — meaningful
  feature for UK planning but needs UI design.
- **Monte Carlo / stochastic projection** — would model sequence-of-returns
  risk properly; currently just have a sensitivity table.
- **Side-by-side scenario compare** — "Plan A vs Plan B" view of two
  retirement configurations.
- **Replace approximate WAS figures with exact ONS tables** — biggest single
  credibility win; still queued from earlier sessions.
- **Region filter** — needs expanded regional WAS data.
- **Mobile layout** — sidebar still feels heavy on mobile despite the tidy.
