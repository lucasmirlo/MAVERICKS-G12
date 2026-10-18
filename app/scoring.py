"""Política de prioridad. Implementación fiel a reference/scoring.py, parametrizada por versión de política.

La prioridad 0–100 ordena casos; no es una probabilidad de quiebra ni de desabastecimiento.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

IMPACT_STATES = {"active", "monitoring", "resolved", "positive", "unrelated", "unclear"}


def number(value, field, minimum=0, maximum=None):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field}: expected finite number")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{field}: outside allowed range")
    return float(value)


def band(policy: dict, score):
    if score is None:
        return None
    for row in reversed(policy["bands"]):
        if score >= row["min"]:
            return row["id"]
    raise ValueError("score outside policy")


def round_half_up(value: float, decimals: int = 1) -> float:
    quantum = Decimal(1).scaleb(-decimals)
    return float(Decimal(str(round(value, 10))).quantize(quantum, rounding=ROUND_HALF_UP))


def inventory_applicability(policy: dict, category: str | None) -> str:
    if category is None:
        return "unknown"
    return "not_applicable" if category in policy["buffer_not_applicable_categories"] else "physical"


def priority(policy: dict, *, is_risk, severity, criticality, single_source, share_category_pct,
             inventory_days=None, lead_days=None, disruption_days=None,
             inventory_applicability="physical", active=True, alternate_affected=False):
    """Prioridad de una pareja evento–proveedor.

    U (dependencia) vale 1 si el proveedor es fuente única o si su alternativo aprobado también está
    afectado por la misma noticia (política ≥ 1.1.0): en ambos casos no hay salida inmediata.

    Inventario físico ausente es revisión, nunca cero días. Para servicios/logística B se omite y
    los pesos se renormalizan. Con active=False la prioridad activa es 0 (el histórico se calcula
    llamando con active=True).
    """
    if not isinstance(is_risk, bool) or not isinstance(active, bool) or not isinstance(alternate_affected, bool):
        raise ValueError("is_risk, active and alternate_affected must be booleans")
    if inventory_applicability not in {"physical", "not_applicable", "unknown"}:
        raise ValueError("invalid inventory applicability")
    if criticality is not None and criticality not in policy["criticality"]:
        raise ValueError("unknown criticality")
    if single_source is not None and single_source not in {"Y", "N"}:
        raise ValueError("unknown single_source")
    severity = number(severity, "severity", 1, 10)
    share = number(share_category_pct, "share_category_pct", 0, 100)
    inventory = number(inventory_days, "inventory_days")
    lead = number(lead_days, "lead_days")
    duration = number(disruption_days, "disruption_days")
    if lead == 0 or duration == 0:
        raise ValueError("lead and disruption duration must be positive when supplied")
    warnings: list[str] = []
    factors: dict[str, float] = {}
    if criticality is not None:
        factors["C"] = policy["criticality"][criticality]
    else:
        warnings.append("criticality_missing")
    if single_source is not None:
        factors["U"] = 1.0 if (single_source == "Y" or alternate_affected) else 0.0
    elif alternate_affected:
        factors["U"] = 1.0
    else:
        warnings.append("single_source_missing")
    if share is not None:
        factors["G"] = share / 100
    else:
        warnings.append("category_share_missing")
    buffers = []
    if inventory_applicability == "not_applicable":
        if inventory is not None:
            raise ValueError("non-applicable inventory must be null")
    elif inventory_applicability == "unknown":
        warnings.append("inventory_applicability_unknown")
    elif inventory is None:
        warnings.append("inventory_missing")
    else:
        if lead is not None:
            buffers.append(max(0.0, min(1.0, (lead - inventory) / lead)))
        if duration is not None:
            buffers.append(max(0.0, min(1.0, (duration - inventory) / duration)))
        if buffers:
            factors["B"] = max(buffers)
        else:
            warnings.append("buffer_horizon_missing")
    if is_risk and severity is None:
        warnings.append("severity_missing")
    weights = policy["weights"]
    denominator = sum(weights[k] for k in factors)
    exposure = sum(weights[k] * v for k, v in factors.items()) / denominator if denominator else None
    contributions = {k: weights[k] * v / denominator for k, v in factors.items()} if denominator else {}
    if not is_risk or not active:
        result = 0.0
    elif severity is None or exposure is None:
        result = None
    else:
        raw = 100 * (severity / 10) * (policy["severity_floor"] + policy["exposure_weight"] * exposure)
        result = round_half_up(raw, policy["rounding"]["decimals"])
    return {
        "priority": result,
        "band": band(policy, result),
        "exposure": exposure,
        "factors": factors,
        "contributions": contributions,
        "warnings": warnings,
        "needs_review": bool(warnings),
        "alternate_affected": alternate_affected,
        "policy_version": policy["version"],
    }


def urgency_rule(policy: dict, *, is_risk: bool, impact_status: str, priority) -> bool:
    """Urgencia por prioridad: riesgo activo con P ≥ thresholds.urgent_priority (política ≥ 1.1.0)."""
    threshold = policy["thresholds"].get("urgent_priority")
    if threshold is None or priority is None:
        return False
    return bool(is_risk and impact_status == "active" and priority >= threshold)


def decisions(policy: dict, *, p_link, p_risk, p_urgent, impact_status="active", needs_review=False):
    values = [number(x, n, 0, 1) for n, x in [("p_link", p_link), ("p_risk", p_risk), ("p_urgent", p_urgent)]]
    if any(x is None for x in values):
        raise ValueError("decision probabilities must be present")
    if impact_status not in IMPACT_STATES:
        raise ValueError("invalid impact_status")
    p_link, p_risk, p_urgent = values
    t = policy["thresholds"]
    linked = p_link >= t["link"]
    risk = linked and p_risk >= t["risk"]
    urgent = risk and p_urgent >= t["urgent"]
    relevant = [p_link] + ([p_risk] if linked else []) + ([p_urgent] if risk else [])
    ambiguous = any(t["review_low"] <= p <= t["review_high"] for p in relevant)
    contradictory = bool(risk and impact_status in {"resolved", "positive", "unrelated"})
    reasons = []
    if ambiguous:
        reasons.append("ambiguous_probability")
    if contradictory:
        reasons.append("contradictory_impact_state")
    if impact_status == "unclear":
        reasons.append("impact_state_unclear")
    review = needs_review or bool(reasons)
    audible = urgent and impact_status == "active" and not review and min(values) >= t["audible_probability"]
    return {
        "linked": linked,
        "is_risk": "Y" if risk else "N",
        "urgent": "Y" if urgent else "N",
        "needs_review": review,
        "review_reasons": reasons,
        "sound_eligible": audible,
    }
