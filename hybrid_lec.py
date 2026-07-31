from __future__ import annotations
import numpy as np


_BRIDGE_POINTS = 120
_WIDENING_FACTORS = (1.0, 1.15, 1.35, 1.65, 2.0, 2.6, 3.4, 4.5, 6.0)


def _prepare_curve(loss, rate):
    """Clean an LEC and order it by increasing loss."""
    loss = np.asarray(loss, dtype=float).ravel()
    rate = np.asarray(rate, dtype=float).ravel()

    if loss.size != rate.size:
        raise ValueError("loss and exceedance rate must have the same length.")

    valid = (
        np.isfinite(loss)
        & np.isfinite(rate)
        & (loss > 0.0)
        & (rate > 0.0)
    )
    loss = loss[valid]
    rate = rate[valid]

    if loss.size < 2:
        raise ValueError("Each curve needs at least two positive finite points.")

    order = np.argsort(loss, kind="mergesort")
    loss = loss[order]
    rate = rate[order]

    # Collapse exact duplicate losses using the largest exceedance rate.
    unique_loss, first = np.unique(loss, return_index=True)
    unique_rate = np.maximum.reduceat(rate, first)

    if unique_loss.size < 2:
        raise ValueError("Each curve needs at least two distinct loss values.")

    # An exceedance rate cannot rise when the loss threshold rises.
    unique_rate = np.minimum.accumulate(unique_rate)
    return unique_loss, unique_rate


def _log_value_and_slope(loss_new, loss, rate):
    """Return log(rate) and the local log-log slope without extrapolation."""
    loss_new = float(loss_new)
    loss_min = float(loss[0])
    loss_max = float(loss[-1])

    # Inverting a curve with exp(log(loss)) can place an endpoint a few
    # floating-point digits outside its original range. Accept only that
    # negligible numerical drift, then snap the value back to the boundary.
    below_range = loss_new < loss_min and not np.isclose(
        loss_new, loss_min, rtol=1e-12, atol=0.0
    )
    above_range = loss_new > loss_max and not np.isclose(
        loss_new, loss_max, rtol=1e-12, atol=0.0
    )
    if below_range or above_range:
        raise ValueError("Interpolation requested outside the curve's loss range.")

    loss_new = float(np.clip(loss_new, loss_min, loss_max))

    log_loss = np.log(loss)
    log_rate = np.log(rate)
    x = np.log(loss_new)

    segment = np.searchsorted(log_loss, x, side="right") - 1
    segment = int(np.clip(segment, 0, log_loss.size - 2))

    slope = (
        (log_rate[segment + 1] - log_rate[segment])
        / (log_loss[segment + 1] - log_loss[segment])
    )
    value = log_rate[segment] + slope * (x - log_loss[segment])
    return float(value), float(slope)


def _loss_at_rate(target_rate, loss, rate):
    """Invert a monotone LEC in log-log space.

    The left edge of a horizontal rate segment is used so a plateau cannot
    push the transition unnecessarily far into the probabilistic tail.
    """
    target_rate = float(np.clip(target_rate, np.min(rate), np.max(rate)))
    unique_rate = np.unique(rate)
    left_loss = np.array(
        [np.min(loss[rate == value]) for value in unique_rate],
        dtype=float,
    )

    inverted_loss = float(
        np.exp(
            np.interp(
                np.log(target_rate),
                np.log(unique_rate),
                np.log(left_loss),
            )
        )
    )

    # Keep a mathematically in-range endpoint inside the exact stored bounds.
    return float(np.clip(inverted_loss, loss[0], loss[-1]))


def _limit_endpoint_slopes(secant, slope_low, slope_high):
    """Limit endpoint slopes so one cubic interval remains monotone."""
    if secant >= 0.0:
        raise ValueError("The bridge endpoints must decrease in exceedance rate.")

    slope_low = min(float(slope_low), 0.0)
    slope_high = min(float(slope_high), 0.0)
    alpha = slope_low / secant
    beta = slope_high / secant
    radius = alpha * alpha + beta * beta

    if radius <= 9.0:
        return slope_low, slope_high, 0.0

    scale = 3.0 / np.sqrt(radius)
    limited_low = scale * alpha * secant
    limited_high = scale * beta * secant
    adjustment = abs(limited_low - slope_low) + abs(limited_high - slope_high)
    return limited_low, limited_high, adjustment


def _evaluate_band(low, high, empirical_loss, empirical_rate,
                   tail_loss, tail_rate):
    """Evaluate whether two loss boundaries can form a decreasing bridge."""
    if high <= low * (1.0 + 1e-12):
        return None

    y_low, slope_low = _log_value_and_slope(
        low, empirical_loss, empirical_rate
    )
    y_high, slope_high = _log_value_and_slope(high, tail_loss, tail_rate)
    if y_high >= y_low:
        return None

    secant = (y_high - y_low) / (np.log(high) - np.log(low))
    _, _, slope_adjustment = _limit_endpoint_slopes(
        secant, slope_low, slope_high
    )
    return slope_adjustment


def _find_blend_band(empirical_loss, empirical_rate, tail_loss, tail_rate):
    """Find both transition boundaries from the curves themselves."""
    shared_rate_high = min(np.max(empirical_rate), np.max(tail_rate))
    shared_rate_low = max(np.min(empirical_rate), np.min(tail_rate))

    if shared_rate_low < shared_rate_high:
        start_rate = shared_rate_high
        end_rate = shared_rate_low
    elif np.max(tail_rate) <= np.min(empirical_rate):
        # The curves have a frequency gap but are in the correct order.
        start_rate = np.min(empirical_rate)
        end_rate = np.max(tail_rate)
    else:
        raise ValueError(
            "The probabilistic curve is not a rarer tail of the historical "
            "curve. Check the curve order and annual-frequency units."
        )

    valid_candidates = []
    for factor in _WIDENING_FACTORS:
        candidate_start_rate = min(
            np.max(empirical_rate), start_rate * factor
        )
        candidate_end_rate = max(np.min(tail_rate), end_rate / factor)

        low = _loss_at_rate(
            candidate_start_rate, empirical_loss, empirical_rate
        )
        high = _loss_at_rate(candidate_end_rate, tail_loss, tail_rate)
        slope_adjustment = _evaluate_band(
            low,
            high,
            empirical_loss,
            empirical_rate,
            tail_loss,
            tail_rate,
        )
        if slope_adjustment is None:
            continue

        score = np.log(factor) + 10.0 * slope_adjustment
        valid_candidates.append((score, low, high))

        # With unchanged endpoint slopes, the narrowest valid band is best.
        if slope_adjustment == 0.0:
            return low, high

    if valid_candidates:
        _, low, high = min(valid_candidates, key=lambda item: item[0])
        return low, high

    # Unusual curve geometry: search native knots and prefer a moderate-width
    # bridge that requires the least endpoint-slope adjustment.
    best = None
    empirical_candidates = empirical_loss[len(empirical_loss) // 2:]
    for low in empirical_candidates:
        for high in tail_loss:
            slope_adjustment = _evaluate_band(
                low,
                high,
                empirical_loss,
                empirical_rate,
                tail_loss,
                tail_rate,
            )
            if slope_adjustment is None:
                continue

            score = (
                abs(np.log(high / low) - np.log(3.0))
                + 8.0 * slope_adjustment
            )
            if best is None or score < best[0]:
                best = (score, float(low), float(high))

    if best is None:
        raise ValueError(
            "No decreasing bridge can connect the curves. Check their units "
            "and confirm that the probabilistic data represent extreme losses."
        )

    return best[1], best[2]


def _build_bridge(loss_low, loss_high, log_rate_low, log_rate_high,
                  slope_low, slope_high):
    """Construct a monotone C1 bridge in log-loss/log-rate space."""
    x_low = np.log(loss_low)
    x_high = np.log(loss_high)
    width = x_high - x_low
    secant = (log_rate_high - log_rate_low) / width
    slope_low, slope_high, _ = _limit_endpoint_slopes(
        secant, slope_low, slope_high
    )

    t = np.linspace(0.0, 1.0, _BRIDGE_POINTS)
    h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
    h10 = t**3 - 2.0 * t**2 + t
    h01 = -2.0 * t**3 + 3.0 * t**2
    h11 = t**3 - t**2

    bridge_log_loss = x_low + t * width
    bridge_log_rate = (
        h00 * log_rate_low
        + h10 * width * slope_low
        + h01 * log_rate_high
        + h11 * width * slope_high
    )

    if np.any(np.diff(bridge_log_rate) > 1e-10):
        raise RuntimeError("The automatically constructed bridge is not monotone.")

    return np.exp(bridge_log_loss), np.exp(bridge_log_rate)


def run_hybrid_lec(emp_loss, emp_aep, tail_loss, tail_aep):
    """Create an automatic historical–probabilistic hybrid LEC.

    Parameters
    ----------
    emp_loss, emp_aep
        Historical loss thresholds and annual exceedance frequencies.
    tail_loss, tail_aep
        Probabilistic extreme-loss thresholds and annual exceedance frequencies.

    Returns
    -------
    hybrid_loss, hybrid_aep, blend_low, blend_high
        The monotone hybrid curve and its automatically selected loss band.
    """
    emp_loss, emp_aep = _prepare_curve(emp_loss, emp_aep)
    tail_loss, tail_aep = _prepare_curve(tail_loss, tail_aep)

    blend_low, blend_high = _find_blend_band(
        emp_loss, emp_aep, tail_loss, tail_aep
    )
    log_rate_low, slope_low = _log_value_and_slope(
        blend_low, emp_loss, emp_aep
    )
    log_rate_high, slope_high = _log_value_and_slope(
        blend_high, tail_loss, tail_aep
    )
    bridge_loss, bridge_aep = _build_bridge(
        blend_low,
        blend_high,
        log_rate_low,
        log_rate_high,
        slope_low,
        slope_high,
    )

    historical_side = emp_loss < blend_low
    probabilistic_side = tail_loss > blend_high
    hybrid_loss = np.concatenate(
        (emp_loss[historical_side], bridge_loss, tail_loss[probabilistic_side])
    )
    hybrid_aep = np.concatenate(
        (emp_aep[historical_side], bridge_aep, tail_aep[probabilistic_side])
    )

    if np.any(np.diff(hybrid_loss) <= 0.0):
        raise RuntimeError("The hybrid loss thresholds are not increasing.")
    if np.any(np.diff(hybrid_aep) > 1e-10):
        raise RuntimeError("The hybrid exceedance frequencies are not decreasing.")

    return hybrid_loss, hybrid_aep