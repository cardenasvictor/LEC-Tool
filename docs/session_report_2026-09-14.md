# LEC Tool: session report, 14 September 2026

**Scope of the session:** integrate the consultant's cost-benefit module (delivery v6), refactor the LEC Tool around a user configuration file, make the ex-ante risk reduction and the PPO optional, persist every output, and move the financing-gap probabilities into a main report.

**Result:** LEC Tool v3.0.0, four commits on `main`. The user edits `config.toml` and runs `python main.py`; everything else follows from the flags in that file.

## 1. Commits

| Commit | Content |
| --- | --- |
| `952b2a0` Integrate CBA v6 package | `cba/` (10 modules) copied from `entrega_completa_v6.zip` with LF endings; review fixes 5.1 and 5.2 applied; `outputs/` ignored; stray statistics CSV removed from the root |
| `660aa0f` Add config.toml, refactor main into stages, save all outputs | `config.toml`, `config_loader.py`, `plots.py`, `reporting.py`, new `main.py`; empty-strategy guard in `risk_management.apply_strategy` |
| `05e11e1` Move financing-gap probabilities to main report; wire DRR-CBA comparison | CBA engine and report adjustments, DRR-CBA comparison, CBA figure saved as figure 09 |
| (this commit) Update documentation | `README.md`, `docs/CONFIG.md`, this report, cleanup |

## 2. What was integrated (CBA)

- The consultant's base modules were byte-identical to the repo's except `hybrid_lec.py`, where the repo holds a newer automatic-blend version. Only `cba/` was taken from the zip; no base module was overwritten.
- Review items closed:
  - 5.1: a loan-type instrument that still passes `interest_rate` now raises a `ValueError` (also caught earlier by the config loader with a message naming the instrument).
  - 5.2: the `cnc.py` docstring now states the Honduras calibration and that every CNC parameter is a config input.
  - 5.5: files written with LF; git normalises on commit.
  - 6.1 (fiscal vs total losses): exposed as `cba.loss_basis = "total" | "fiscal"`; default `total` keeps the delivered behaviour. The obsolete TODO in `engine.run_cba` was replaced by a comment and the choice is printed in the CBA report header.
  - 6.2 (DRR-CBA comparison): when both DRR and CBA are enabled, `run_cba` runs a second time on the reduced catalogue with the re-evaluated payouts, and `cba.diagnostics.compute_drr_analysis` fills the "DRR cost-effectiveness" section and figure rows. The report text that claimed instruments were not re-evaluated on the reduced catalogue was corrected.
- Other CBA changes: `run_cba` accepts `gap_thresholds` and `loss_basis`; the CBA text report shows unpaid-loss percentiles instead of the gap probabilities (moved to the main report) and adds the median CNC % saving; `generate_plots` returns a figure instead of forcing the Agg backend and writing a file; the empty sensitivity panel is hidden; the boxplot uses the current matplotlib keyword.

## 3. What was refactored

- **Configuration:** every user input previously hardcoded in `main.py` lives in `config.toml` (run id, output options, input files, LEC options including bootstrap samples, PML return periods and gap fractions, simulation, fiscal share, instruments with optional CBA cost overrides, risk reduction, CBA with per-type cost defaults and CNC calibration). `config_loader.py` validates the file and builds the `drm_configs` list and the `LECCBAConfig` object. The discount horizon and simulation count of the CBA are taken from `[simulation]`, so present values always cover the full catalogue length.
- **Entry point:** `main.py` is a thin orchestrator with one function per stage. Risk reduction runs only with `risk_reduction.enabled = true`; the CBA only with `cba.enabled = true` and at least one instrument.
- **PPO:** the schedule is attached by instrument type, never by list position, and the schedule file is read only when a `ppo` instrument exists. A `ppo` without a `ccf` is rejected at configuration time with a clear message instead of failing inside `apply_strategy`.
- **Outputs:** `outputs/<id>/` holds nine figures (fixed numbering, so file names are stable when stages are skipped), the main report, the statistics CSV, the CBA report and a copy of the configuration. Figures are saved only; `run.show_figures = true` also opens them.
- **Main report** (`<id>_report.txt`): run header, LEC summary (AAL empirical and hybrid, maximum curve loss, maximum historical event, PML per return period), strategy statistics per scenario, financing-gap probabilities at 25/50/75/100 % of the maximum LEC loss (gap = total uncovered loss over the horizon per simulation, undiscounted), DRR summary with the year-by-year reduction schedule and median payback, cumulative-loss statistics, CBA headline, and the list of files.
- Figure and report labels are in English; the README stays in Spanish.

## 4. Verification

All checks were run from the scratchpad; no test file was added to the repository.

| Check | Result |
| --- | --- |
| Consultant's four test batteries against the repo `cba/` (after Stage 1 and again after Stage 3) | 105/105 pass |
| Default `config.toml` (seed 99, 1000 simulations) vs the pre-refactor `statistics_Estrategia 3.csv` | identical: 1382.8 / 544.2 / 217.3 / 618.9 / 130.4 / 371.3 (base) and 1276.0 / 543.8 / 173.6 / 558.1 / 104.2 / 334.9 (reduced) |
| Variants: no PPO, DRR off, CBA off (60 simulations) | exit 0, expected file sets (12 / 9 / 11 files) |
| Four combinations PPO on/off × DRR on/off with CBA on (30 simulations) | expected files, gap section in main report, gap block absent from CBA report, DRR section present only with DRR, PPO present only when declared |
| Visual check of figures 04 and 09 | correct |

Default-run CBA headline (Estrategia 3, 1000 simulations): E[B/C] 1.128, P(B/C > 1) 91.8 %, expected unpaid loss (PV) $1,409.7 MM, B/UL 0.468, DRR B/C direct 2.352 and indirect 2.322. These differ from the consultant's Estrategia 2 figures because the repo's strategy (DDO payouts 80 and 110 instead of 40) and hybrid-curve module differ.

## 5. Observations for the team

- **CNC "expected % saving" is unstable.** The mean of the per-simulation ratio is dominated by simulations with a tiny ex-post cost (it was −25.5 % on the default run while the expected net saving was +$151.5 MM and the ex-ante strategy was cheaper in 92 % of simulations). The median % saving is now printed next to it; consider dropping the mean ratio from presentations.
- **CNC calibration is Honduras-specific** (GDP, SOFR, sovereign spread, tiers). The values are now visible in `[cba.cnc]` and must be changed for any other country.
- **Unused CBA configuration classes.** `GovernmentExposureConfig` and `DRRConfig` in `cba/config.py` are not used by the pipeline (the DRR schedule comes from `risk_reduction.py`). They were left untouched.
- **Sensitivity analysis** exists as a data structure in `cba/diagnostics.py` but was never implemented by the consultant; the corresponding panel is hidden.
- **PML beyond the curve.** If a requested return period is rarer than the smallest exceedance rate of the curve, the report flags that the PML is capped at the curve maximum.
- **Model constants left in code on purpose:** the CCF affected-persons power law, the hybrid-blend constants and histogram bin counts.

## 6. Cleanup

`entrega_completa_v6.zip`, `revision_entrega_v6.md` and the stale `__pycache__` folders were removed from the working tree at the end of the session (none were tracked). The consultant's test batteries, `main_capture.py`, `LEEME.md` and `CAMBIOS_v6.md` were not added to the repository, as requested.
