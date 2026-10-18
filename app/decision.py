"""Decisión por pareja noticia–proveedor y agregación por artículo (política ≥ 1.1.0).

Función pura: no accede a la base de datos ni llama a JEV o al LLM. La usan el pipeline tras JEV, la
adjudicación del LLM y scripts/calibrate_urgency.py, de modo que la decisión exportada y su explicación
salen siempre del mismo cálculo.

- Vínculo y riesgo: probabilidades Noul de JEV con los umbrales de la política (o el LLM en casos dudosos).
- Urgencia: regla `is_risk and impact_status == "active" and P >= thresholds.urgent_priority`.
  `p_urgent` de JEV es segunda opinión: si coincide con la regla la decisión es firme (`regla+jev`);
  si no, el caso es dudoso y lo decide el LLM (`llm`) o se conserva la regla (`regla`).
"""
from __future__ import annotations

from typing import Any

from . import scoring

JEV = "jev"
FIRM = "regla+jev"
MODES = ("jev", "regla_y_jev", "llm")
RULE = "regla"
LLM = "llm"
HUMAN = "humano"
LLM_DECISIVE = {"alta", "media"}
INFERRED_LINK_MAX = 0.80  # vínculo solo por región inferida por debajo de esto es dudoso


def doubt_reasons(policy: dict, pair: dict, *, linked: bool, urgent_rule: bool, jev_urgent: bool) -> list[str]:
    t = policy["thresholds"]
    reasons = []
    if urgent_rule != jev_urgent:
        reasons.append("urgency_disagreement")
    in_band = lambda p: t["review_low"] <= p <= t["review_high"]  # noqa: E731
    if in_band(pair["p_link"]) or (linked and in_band(pair["p_risk"])):
        reasons.append("probability_in_review_band")
    if pair.get("link_basis") == "inferred_region" and linked and pair["p_link"] < INFERRED_LINK_MAX:
        reasons.append("inferred_region_link")
    return reasons


def evaluate_article(policy: dict, pairs: list[dict], suppliers: dict[str, Any], *, event_type: str | None,
                     mode: str = "llm") -> list[dict]:
    """pairs: dicts con supplier_id, p_link, p_risk, p_urgent, severity_jev, severity_confidence, impact_status,
    impact_confidence, has_evidence, duration_days, link_basis, llm (dict | None), llm_status, manual (dict | None).
    Devuelve un dict de resultado por pareja, en el mismo orden.

    mode (sprint 3): "jev" decide Urgent con p_urgent de JEV; "regla_y_jev" exige regla P y JEV; "llm" deja que el
    LLM decida los casos dudosos (sprint 2). En los dos primeros la opinión del LLM solo se muestra para revisión."""
    if mode not in MODES:
        raise ValueError(f"URGENCY_MODE desconocido: {mode}")
    t = policy["thresholds"]
    base = []
    for pair in pairs:
        dec = scoring.decisions(policy, p_link=pair["p_link"], p_risk=pair["p_risk"], p_urgent=pair["p_urgent"],
                                impact_status=pair["impact_status"])
        llm = pair.get("llm") or None
        confident = bool(mode == "llm" and llm and llm.get("confianza") in LLM_DECISIVE)
        manual = pair.get("manual") or None
        if manual:
            linked, is_risk = bool(manual["vinculado"]), bool(manual["vinculado"] and manual["es_riesgo"])
        elif confident:
            linked, is_risk = bool(llm["vinculado"]), bool(llm["vinculado"] and llm["es_riesgo"])
        else:
            linked, is_risk = dec["linked"], dec["is_risk"] == "Y"
        base.append((pair, dec, linked, is_risk, confident, manual))
    accepted_ids = {pair["supplier_id"] for pair, _, linked, *_ in base if linked}

    results = []
    for pair, dec, linked, is_risk, confident, manual in base:
        s = suppliers[pair["supplier_id"]]
        reasons = list(dec["review_reasons"])
        alternate_affected = bool(s.alternate_id and s.alternate_id in accepted_ids)
        severity = pair.get("severity_jev")
        applicability = scoring.inventory_applicability(policy, s.category)
        try:
            pr = scoring.priority(policy, is_risk=is_risk, severity=severity if is_risk else None, criticality=s.criticality,
                                  single_source=s.single_source, share_category_pct=s.share_category_pct,
                                  inventory_days=s.inventory_days, lead_days=s.lead_days,
                                  disruption_days=pair.get("duration_days"), inventory_applicability=applicability,
                                  active=True, alternate_affected=alternate_affected)
        except ValueError:
            pr = None
            reasons.append("invalid_supplier_data")
        priority = pr["priority"] if pr else None
        urgent_rule = scoring.urgency_rule(policy, is_risk=is_risk, impact_status=pair["impact_status"], priority=priority)
        jev_linked = dec["linked"]
        jev_risk = dec["is_risk"] == "Y"
        jev_urgent = bool(jev_risk and pair["p_urgent"] >= t["urgent"])
        jev_rule = scoring.urgency_rule(policy, is_risk=jev_risk, impact_status=pair["impact_status"], priority=priority)
        doubts = doubt_reasons(policy, pair, linked=jev_linked, urgent_rule=jev_rule, jev_urgent=jev_urgent)
        llm = pair.get("llm") or None
        llm_status = pair.get("llm_status") or ("pendiente" if doubts else "no_necesaria")

        if manual:
            urgent, source = bool(is_risk and manual["urgente"]), HUMAN
            reasons = [r for r in reasons if r != "ambiguous_probability"]
        elif confident:
            urgent, source = bool(is_risk and llm["urgente"]), LLM
            reasons = [r for r in reasons if r not in ("ambiguous_probability", "contradictory_impact_state")]
        elif mode == "jev":
            urgent, source = jev_urgent, JEV
        elif mode == "regla_y_jev":
            urgent, source = bool(urgent_rule and jev_urgent), FIRM
        elif doubts:
            urgent, source = urgent_rule, RULE
            if llm and llm.get("confianza") == "baja":
                reasons.append("llm_low_confidence")
            elif llm_status == "sin_segunda_opinion":
                reasons.append("sin_segunda_opinion")
            elif llm_status == "pendiente":
                reasons.append("second_opinion_pending")
        else:
            urgent, source = urgent_rule, FIRM

        opinion = llm if (llm and llm.get("confianza") in LLM_DECISIVE) else None
        if mode != "llm" and opinion and not manual:
            # La IA no decide en estos modos: si discrepa con firmeza, la pareja va a revisión humana con su propuesta.
            if (bool(opinion["vinculado"]) != linked or bool(opinion["vinculado"] and opinion["es_riesgo"]) != is_risk
                    or bool(opinion["urgente"]) != bool(urgent and is_risk)):
                reasons.append("llm_disagrees")
        if linked and pair.get("impact_confidence") is not None and pair["impact_confidence"] < t["choice_score_confidence"] and source not in (LLM, HUMAN):
            reasons.append("low_impact_state_confidence")
        if is_risk and pair.get("severity_confidence") is not None and pair["severity_confidence"] < t["choice_score_confidence"]:
            reasons.append("low_severity_confidence")
        if is_risk and not pair.get("has_evidence"):
            reasons.append("no_evidence")
        if s.data_issues and linked:
            reasons.append("supplier_data_issue")
        if pr and is_risk:
            reasons += pr["warnings"]
            if priority is None:
                reasons.append("priority_unavailable")
        reasons = list(dict.fromkeys(reasons))
        needs_review = bool(reasons)
        active_priority = 0.0 if pair["impact_status"] == "resolved" else priority
        if not is_risk:
            urgent = False
        # Sonido solo con decisión firme: regla+JEV con probabilidades altas, IA con confianza alta o persona.
        # Una regla sin segunda opinión o un vínculo solo regional inferido no suenan.
        firm_enough = ((source == JEV and min(pair["p_link"], pair["p_risk"], pair["p_urgent"]) >= t["audible_probability"])
                       or (source == FIRM and pair["p_link"] >= t["audible_probability"] and pair["p_risk"] >= t["audible_probability"])
                       or (source == LLM and llm.get("confianza") == "alta") or source == HUMAN)
        sound = bool(urgent and pair["impact_status"] == "active" and not needs_review and firm_enough
                     and pair.get("link_basis") != "inferred_region")
        results.append({
            "supplier_id": pair["supplier_id"], "accepted": linked, "is_risk": "Y" if is_risk else "N", "urgent": "Y" if urgent else "N",
            "urgent_rule": urgent_rule, "jev_urgent": jev_urgent, "doubtful": bool(doubts), "doubt_reasons": doubts,
            "decision_source": source, "llm_status": llm_status if doubts else "no_necesaria",
            "severity": severity if is_risk else None, "priority": priority, "active_priority": active_priority,
            "priority_band": scoring.band(policy, active_priority) if active_priority is not None else None,
            "exposure": pr["exposure"] if pr else None, "factor_values": pr["factors"] if pr else {},
            "contributions": pr["contributions"] if pr else {}, "alternate_affected": alternate_affected,
            "review_reasons": reasons, "needs_review": needs_review, "sound_eligible": sound,
            "is_recovery": bool(linked and (pair["impact_status"] == "resolved" or event_type == "recovery")),
        })
    return results


def aggregate(results: list[dict]) -> dict:
    accepted = [r for r in results if r["accepted"]]
    is_risk = any(r["is_risk"] == "Y" for r in accepted)
    return {
        "affected_supplier_ids": sorted({r["supplier_id"] for r in accepted}),
        "is_risk": "Y" if is_risk else "N",
        "urgent": "Y" if is_risk and any(r["is_risk"] == "Y" and r["urgent"] == "Y" for r in accepted) else "N",
    }
