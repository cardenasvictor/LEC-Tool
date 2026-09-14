"""
cba/cnc.py — Costo Neto Comparado (CNC)
========================================
Comparative Net Cost indicator (modular, optional).

Compares two financing strategies over the simulated catalogue, on a SYMMETRIC
basis: both strategies finance the SAME amount of coverage. The only difference
is the cost of financing it.

  Strategy A (ex-ante instruments):
    The cost of holding the portfolio of ex-ante instruments
    (CCRIF + PPO + CCF + DDO) that delivered the coverage. This is the present
    value of all instrument costs already computed by the CBA engine. DRR is
    excluded.

  Strategy B (ex-post commercial debt):
    The cost of financing the SAME coverage amount (the instrument payouts)
    with sovereign commercial debt issued AFTER the event, at a market rate
    whose spread widens with the size of the EVENT as a share of GDP.

The indicator answers a clean, educational question: for the same amount of
coverage, is it cheaper to hold the ex-ante instruments or to borrow
commercially after the event? By matching the financed amount, the indicator
isolates the financing-cost differential (the spread effect) and avoids the
misleading size effect that would arise if Strategy B financed the full loss
while Strategy A covered only a fraction.

The endogenous market rate captures the empirical fact (and the BID HO-O0008
Honduras analysis) that sovereign spreads widen sharply after catastrophic
events — so the ex-ante strategy tends to win more clearly for the large, rare
events, but by a credible margin driven by the rate differential, not by an
accounting artefact.

NOTE: Strategy A's residual unpaid loss is a separate matter, reported by the
unpaid-loss indicators. The CNC is about financing cost for matched coverage,
not about adequacy of coverage.

DESIGN
------
- Pure module: no file I/O, no plotting, no web access.
- Reuses loan_pv_at_disbursement from costs.py so the ex-post debt is valued
  with EXACTLY the same full-cost-at-disbursement methodology as PPO/CCF/DDO
  (Clarke, Mahul, Poulter & Teh 2017).
- Annual basis, consistent with the rest of the module.
- Fully modular: gated by CNCConfig.enabled. Remove the module or set the flag
  to False and nothing else breaks.

CALIBRATION STATUS (v6): the default economic parameters are calibrated for
Honduras, the example loss curve: GDP from the World Bank (current US$, 2024),
base rate from SOFR (NY Fed, mid-2026), sovereign base spread of 500 bps from
the BID HO-O0008 Honduras contingent-credit economic analysis, and the tier
structure informed by Cavallo, Becerra & Acevedo (IDB-WP-1257). Tier thresholds
and spread magnitudes are an informed calibration by the analyst. All of these
values are user inputs in config.toml ([cba.cnc]) and must be re-calibrated for
any other country.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple

from .costs import loan_pv_at_disbursement


# ============================================================
# Configuration
# ============================================================

# Endogenous spread tiers: ordered list of (upper_threshold_as_share_of_GDP,
# additional_spread). The spread applied to an event is the one of the first
# tier whose upper threshold the event's loss/GDP ratio does NOT exceed.
#
# CALIBRATION (v6): the tier STRUCTURE is informed by the empirical finding of
# Cavallo, Becerra & Acevedo (IDB Working Paper No. IDB-WP-1257) that the
# macroeconomic impact of disasters is strongly non-linear and threshold-like:
# mild and moderate events show no significant impact on GDP growth, while only
# catastrophic events (the extreme tail) cause persistent output losses, and the
# damage is larger for poorer countries. Accordingly the spread stays at its
# base level for small/moderate events and jumps only in the catastrophic tail.
#
# The threshold VALUES (2% and 5% of GDP) are an informed calibration by the
# analyst, not a number Cavallo reports directly: his loss figure (2.1 to 3.7
# percentage points) refers to the GDP-growth loss, not to the event size as a
# share of GDP. The thresholds capture the SHAPE of the relationship (flat for
# non-catastrophic events, steep in the tail), which is what the evidence
# supports. Spread magnitudes are likewise an informed calibration.
DEFAULT_SPREAD_TIERS: List[Tuple[float, float]] = [
    (0.02, 0.000),         # event < 2% of GDP    -> +0 bps (no macro impact)
    (0.05, 0.015),         # 2% <= event < 5%     -> +150 bps (onset of damage)
    (float('inf'), 0.05),  # event >= 5% of GDP   -> +500 bps (catastrophic tail)
]


@dataclass
class CNCConfig:
    """
    Configuration for the Comparative Net Cost indicator.

    Economic parameters calibrated for Honduras (the example loss curve).
    Sources:
      - gdp: World Bank, GDP current US$, Honduras 2024 (USD 37,094 MM).
      - base_rate: SOFR reference (~3.5% mid-2026, NY Fed).
      - sovereign_base_spread: 500 bps, BID HO-O0008 Honduras (rating B).
      - spread_tiers: structure informed by Cavallo, Becerra & Acevedo
        (IDB-WP-1257); threshold and spread magnitudes are an informed
        calibration by the analyst (see DEFAULT_SPREAD_TIERS note).
    """
    enabled: bool = True

    # GDP of reference (M USD). Honduras 2024, World Bank current US$.
    gdp: float = 37094.0

    # International base rate (SOFR-like). SOFR ~3.5% mid-2026 (NY Fed).
    base_rate: float = 0.035

    # Sovereign base spread in ordinary conditions. 500 bps from BID HO-O0008
    # Honduras 10-year commercial sovereign debt (rating B).
    sovereign_base_spread: float = 0.05

    # Endogenous spread tiers (see DEFAULT_SPREAD_TIERS).
    spread_tiers: List[Tuple[float, float]] = field(
        default_factory=lambda: list(DEFAULT_SPREAD_TIERS)
    )

    # Ex-post commercial debt repayment term (years).
    ex_post_term_years: int = 10

    def __post_init__(self):
        # Defensive validation: stop on absurd configuration rather than
        # produce a false indicator.
        if not np.isfinite(self.gdp) or self.gdp <= 0:
            raise ValueError(
                f"CNCConfig: gdp must be a positive finite number, got {self.gdp}. "
                f"GDP is the denominator for event severity; zero or negative GDP "
                f"would make every event look negligible and the spread always zero."
            )
        if not (0.0 <= self.base_rate <= 1.0):
            raise ValueError(
                f"CNCConfig: base_rate must be in [0, 1], got {self.base_rate}."
            )
        if not (0.0 <= self.sovereign_base_spread <= 1.0):
            raise ValueError(
                f"CNCConfig: sovereign_base_spread must be in [0, 1], got "
                f"{self.sovereign_base_spread}."
            )
        if self.ex_post_term_years <= 0:
            raise ValueError(
                f"CNCConfig: ex_post_term_years must be > 0, got "
                f"{self.ex_post_term_years}."
            )


@dataclass
class CNCResults:
    """Results of the Comparative Net Cost analysis."""
    # Per-simulation arrays, shape (num_sims,)
    cost_a_pv: np.ndarray = None      # ex-ante instruments cost (PV)
    cost_b_pv: np.ndarray = None      # ex-post commercial debt cost (PV)
    net_saving: np.ndarray = None     # cost_b - cost_a (positive => A cheaper)
    pct_saving: np.ndarray = None     # (cost_b - cost_a) / cost_b

    # Aggregated metrics
    expected_net_saving: float = 0.0
    median_net_saving: float = 0.0
    p10_net_saving: float = 0.0
    p90_net_saving: float = 0.0
    expected_pct_saving: float = 0.0
    median_pct_saving: float = 0.0
    prob_positive_saving: float = 0.0   # P(ex-ante strategy is cheaper)

    # Over-coverage diagnostics: cells (sim-year) where the instrument payout
    # exceeds the event loss. This can happen legitimately under the model's
    # parallel-evaluation overlap (a known feature carried over from the BID
    # code). The CNC does not stop on it; it surfaces the count so the user can
    # see whether overlap is material, rather than discovering it by reading code.
    n_overcoverage_cells: int = 0       # cells with payout > loss
    n_payout_cells: int = 0             # cells with payout > 0 (denominator)
    pct_overcoverage: float = 0.0       # share of payout cells that over-cover
    max_overcoverage_ratio: float = 0.0  # worst payout/loss ratio observed


# ============================================================
# Endogenous market rate
# ============================================================

def endogenous_spread(loss_share_of_gdp: float,
                      tiers: List[Tuple[float, float]] = None) -> float:
    """
    Return the additional sovereign spread for an event whose loss equals
    `loss_share_of_gdp` of GDP, using the tiered schedule.

    The spread is that of the first tier whose upper threshold is not exceeded.
    """
    if tiers is None:
        tiers = DEFAULT_SPREAD_TIERS
    for upper_threshold, spread in tiers:
        if loss_share_of_gdp < upper_threshold:
            return spread
    # Fallback: last tier (should be unreachable if last threshold is inf)
    return tiers[-1][1]


def ex_post_debt_cost_for_amount(
    financed_amount: float,
    event_loss: float,
    cnc_cfg: CNCConfig,
    social_rate: float,
) -> float:
    """
    Present value (at the disbursement year) of financing `financed_amount`
    with ex-post commercial sovereign debt.

    Key separation: the MARKET RATE's endogenous spread is driven by the size
    of the EVENT relative to GDP (event_loss/GDP) — that is, by the severity of
    the disaster, which is what moves sovereign spreads. The AMOUNT financed is
    `financed_amount` (the instrument coverage being matched), which may be much
    smaller than the event loss. This keeps the comparison symmetric with the
    ex-ante strategy while still letting the spread reflect event severity.

    The debt is a 10-year amortising loan, valued with the same
    loan_pv_at_disbursement used for PPO/CCF/DDO.
    """
    if financed_amount <= 0:
        return 0.0
    share = event_loss / cnc_cfg.gdp if cnc_cfg.gdp > 0 else 0.0
    market_rate = (
        cnc_cfg.base_rate
        + cnc_cfg.sovereign_base_spread
        + endogenous_spread(share, cnc_cfg.spread_tiers)
    )
    return loan_pv_at_disbursement(
        principal=financed_amount,
        loan_rate=market_rate,
        social_rate=social_rate,
        term_years=cnc_cfg.ex_post_term_years,
        grace_years=0,
    )


# ============================================================
# Main computation
# ============================================================

def compute_cnc(
    losses_matrix: np.ndarray,
    payouts_matrix: np.ndarray,
    cost_a_pv: np.ndarray,
    cnc_cfg: CNCConfig,
    social_rate: float,
) -> CNCResults:
    """
    Compute the Comparative Net Cost indicator (symmetric comparison).

    Both strategies move the SAME amount of money: the coverage actually
    provided by the ex-ante instruments. The only difference is the cost of
    financing that amount.

      Strategy A: cost of the ex-ante instruments (primas, fees, debt service)
                  that delivered the coverage. This is cost_a_pv.
      Strategy B: cost of financing the SAME coverage amount with ex-post
                  commercial debt, at a market rate whose spread widens with
                  event size relative to GDP.

    This symmetric design isolates the financing-cost differential (the spread
    effect) and removes the misleading size effect that arises when Strategy B
    finances the full loss while Strategy A covers only a fraction. For an
    educational tool this is the honest comparison: for the same coverage, is
    the ex-ante instrument cheaper than borrowing ex-post?

    Parameters
    ----------
    losses_matrix : np.ndarray, shape (num_sims, horizon)
        Annual losses per simulation. Used only to size the event relative to
        GDP for the endogenous spread (the spread reflects the severity of the
        event, not the amount financed).
    payouts_matrix : np.ndarray, shape (num_sims, horizon)
        Annual total instrument payouts per simulation. This is the amount that
        Strategy B must finance commercially (same coverage as Strategy A).
    cost_a_pv : np.ndarray, shape (num_sims,)
        Present value of the ex-ante instruments' total cost per simulation.
    cnc_cfg : CNCConfig
    social_rate : float
        Social discount rate.

    Returns
    -------
    CNCResults
    """
    losses_matrix = np.asarray(losses_matrix, dtype=float)
    payouts_matrix = np.asarray(payouts_matrix, dtype=float)

    # --- Defensive validation: stop on absurd inputs ---
    if not np.all(np.isfinite(losses_matrix)):
        raise ValueError(
            "compute_cnc: losses_matrix contains non-finite values (NaN/inf). "
            "A single NaN would silently contaminate the aggregate metrics."
        )
    if not np.all(np.isfinite(payouts_matrix)):
        raise ValueError(
            "compute_cnc: payouts_matrix contains non-finite values (NaN/inf)."
        )
    if np.any(losses_matrix < 0):
        raise ValueError(
            "compute_cnc: losses_matrix contains negative values. Losses are "
            "non-negative by definition; check the input catalogue."
        )
    if np.any(payouts_matrix < 0):
        raise ValueError(
            "compute_cnc: payouts_matrix contains negative values. Instrument "
            "payouts are non-negative by definition; check the strategy output."
        )
    if losses_matrix.shape != payouts_matrix.shape:
        raise ValueError(
            f"compute_cnc: losses_matrix {losses_matrix.shape} and payouts_matrix "
            f"{payouts_matrix.shape} must have the same shape."
        )

    num_sims, horizon = losses_matrix.shape

    # Strategy B: finance the SAME coverage the instruments delivered, with
    # ex-post commercial debt. The market rate's endogenous spread is driven by
    # the EVENT size relative to GDP (severity), while the financed amount is
    # the instrument payout for that period (symmetry with Strategy A).
    cost_b_pv = np.zeros(num_sims)
    for s in range(num_sims):
        total = 0.0
        for t in range(horizon):
            financed = payouts_matrix[s, t]
            if financed > 0:
                event_loss = losses_matrix[s, t]
                pv_at_t = ex_post_debt_cost_for_amount(
                    financed_amount=financed,
                    event_loss=event_loss,
                    cnc_cfg=cnc_cfg,
                    social_rate=social_rate,
                )
                total += pv_at_t * (1.0 + social_rate) ** (-t)
        cost_b_pv[s] = total

    results = CNCResults()
    results.cost_a_pv = np.asarray(cost_a_pv, dtype=float)
    results.cost_b_pv = cost_b_pv
    results.net_saving = cost_b_pv - results.cost_a_pv

    # Percentage saving = (cost_b - cost_a) / cost_b, guarding cost_b == 0.
    with np.errstate(divide='ignore', invalid='ignore'):
        pct = np.where(cost_b_pv > 0,
                       (cost_b_pv - results.cost_a_pv) / cost_b_pv,
                       np.nan)
    results.pct_saving = pct

    # Aggregates
    results.expected_net_saving = float(np.mean(results.net_saving))
    results.median_net_saving = float(np.median(results.net_saving))
    results.p10_net_saving = float(np.percentile(results.net_saving, 10))
    results.p90_net_saving = float(np.percentile(results.net_saving, 90))
    results.prob_positive_saving = float(np.mean(results.net_saving > 0))

    finite_pct = pct[np.isfinite(pct)]
    if len(finite_pct) > 0:
        results.expected_pct_saving = float(np.mean(finite_pct))
        results.median_pct_saving = float(np.median(finite_pct))

    # Over-coverage diagnostic (option C): count cells where payout > loss,
    # without stopping the run. Tolerance avoids flagging rounding noise.
    tol = 1e-6
    payout_cells = payouts_matrix > tol
    results.n_payout_cells = int(np.sum(payout_cells))
    overcover = payouts_matrix > (losses_matrix + tol)
    results.n_overcoverage_cells = int(np.sum(overcover))
    if results.n_payout_cells > 0:
        results.pct_overcoverage = (
            results.n_overcoverage_cells / results.n_payout_cells
        )
    if results.n_overcoverage_cells > 0:
        # Worst payout/loss ratio among over-covering cells (loss>0 only).
        mask = overcover & (losses_matrix > tol)
        if np.any(mask):
            ratios = payouts_matrix[mask] / losses_matrix[mask]
            results.max_overcoverage_ratio = float(np.max(ratios))
        else:
            # Over-coverage only where loss==0 (payout on a no-loss period).
            results.max_overcoverage_ratio = float('inf')

    return results
