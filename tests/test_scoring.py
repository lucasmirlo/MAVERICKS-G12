"""Invariantes de la política y coherencia con reference/scoring.py."""
import importlib.util
import itertools

import pytest

from app import scoring
from app.config import ROOT, file_policy

POLICY = file_policy()
spec = importlib.util.spec_from_file_location("ref_scoring", ROOT / "reference" / "scoring.py")
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)


def case(**kw):
    values = dict(is_risk=True, severity=9, criticality="High", single_source="Y", share_category_pct=40, inventory_days=30, lead_days=90)
    values.update(kw)
    return scoring.priority(POLICY, **values)


def test_hand_calculated_example():
    assert case()["priority"] == 83.6
    assert case()["factors"]["B"] == pytest.approx(2 / 3)
    assert case()["band"] == "critical"


def test_matches_reference_on_grid():
    for sev, crit, ss, share, inv, lead, dur, appl, active in itertools.product(
            [1, 4.5, 7.25, 10], ["High", "Medium", "Low", None], ["Y", "N", None], [0, 12.5, 100, None],
            [0, 30, None], [90, None], [None, 45, 180], ["physical", "not_applicable"], [True, False]):
        if appl == "not_applicable" and inv is not None:
            continue
        kwargs = dict(is_risk=True, severity=sev, criticality=crit, single_source=ss, share_category_pct=share, inventory_days=inv,
                      lead_days=lead, disruption_days=dur, inventory_applicability=appl, active=active)
        assert scoring.priority(POLICY, **kwargs) == ref.priority(**kwargs)


def test_nonrisk_resolution_bounds_and_single_source_once():
    assert case(is_risk=False)["priority"] == 0
    assert case(active=False)["priority"] == 0
    assert case(single_source="N")["priority"] == 70.1
    for s in range(1, 11):
        assert 0 <= case(severity=s)["priority"] <= 100


def test_unknown_inventory_is_review_not_zero():
    unknown = case(inventory_days=None)
    assert "B" not in unknown["factors"] and "inventory_missing" in unknown["warnings"]
    assert case(inventory_days=0)["factors"]["B"] == 1


def test_services_omit_buffer_without_review():
    r = case(inventory_days=None, inventory_applicability="not_applicable")
    assert "B" not in r["factors"] and not r["needs_review"]


def test_invalid_data_rejected():
    for override in [dict(share_category_pct=101), dict(lead_days=0), dict(inventory_days=-1), dict(severity=float("nan")),
                     dict(severity=11), dict(criticality="Unknown")]:
        with pytest.raises(ValueError):
            case(**override)


def test_decisions_match_reference():
    for pl, pr, pu, st in itertools.product([0.1, 0.4, 0.55, 0.7, 0.9], [0.1, 0.5, 0.85], [0.2, 0.6, 0.95],
                                            ["active", "resolved", "positive", "unclear", "monitoring"]):
        mine = scoring.decisions(POLICY, p_link=pl, p_risk=pr, p_urgent=pu, impact_status=st)
        theirs = ref.decisions(p_link=pl, p_risk=pr, p_urgent=pu, impact_status=st)
        assert {k: mine[k] for k in theirs} == theirs


def test_positive_keeps_link_and_confidence_independent():
    positive = scoring.decisions(POLICY, p_link=.99, p_risk=.01, p_urgent=.95, impact_status="positive")
    assert positive["linked"] and positive["is_risk"] == "N" and positive["urgent"] == "N" and not positive["sound_eligible"]
    before = case()["priority"]
    scoring.decisions(POLICY, p_link=.55, p_risk=.99, p_urgent=.99)
    assert case()["priority"] == before
