"""Constructor de peticiones, cliente HTTP y validación de respuestas."""
import json

import httpx
import pytest

from app.config import file_policy
from app.jev.client import JevClient, JevError
from app.jev.questions import stage_a, stage_b
from app.jev.validate import InvalidJevResponse, validate_answers
from app.textutil import duration_candidates, sentences

from .helpers import SYNTHETIC_SUPPLIERS

POLICY = file_policy()
ARTICLE = {"news_id": "EX001", "headline": "A plant stopped.", "summary": "Aster Labs reports a two-day shutdown. Deliveries may be delayed.",
           "Is_Risk": "SECRET_LABEL", "Explanation": "ANSWER_KEY_MARKER", "Affected_Supplier_IDs": "EXS01", "Event_Type": "LABEL_TYPE"}


def test_whitelist_excludes_labels():
    for body in [stage_a(POLICY, ARTICLE, SYNTHETIC_SUPPLIERS, "jev-1.13.0"), stage_b(POLICY, ARTICLE, SYNTHETIC_SUPPLIERS, [], "jev-1.13.0")]:
        encoded = json.dumps(body)
        for marker in ("SECRET_LABEL", "ANSWER_KEY_MARKER", "LABEL_TYPE", "Is_Risk", "Explanation", "Affected_Supplier_IDs"):
            assert marker not in encoded


def test_stage_a_one_noul_per_supplier_and_named():
    q = stage_a(POLICY, ARTICLE, SYNTHETIC_SUPPLIERS, "jev-1.13.0")["questions"]
    for s in SYNTHETIC_SUPPLIERS:
        assert q[f"linked_{s['supplier_id']}"]["type"] == "noul"
        assert s["name"] in q[f"linked_{s['supplier_id']}"]["instructions"]
        assert s["supplier_id"] in q[f"linked_{s['supplier_id']}"]["instructions"]
    assert q["event_type"]["type"] == "choice" and q["event_state"]["type"] == "choice"
    assert len(q) == len(SYNTHETIC_SUPPLIERS) + 2


def test_stage_b_batches_all_candidates_in_one_body():
    body = stage_b(POLICY, ARTICLE, SYNTHETIC_SUPPLIERS[:2], duration_candidates(ARTICLE), "jev-1.13.0")
    assert len(body["questions"]) == 12
    assert len(body["questions"]["severity_EXS01"]["criteria"]) == 10
    assert "unknown" in body["questions"]["duration_EXS02"]["criteria"]
    assert "none" in body["questions"]["evidence_EXS01"]["criteria"]


def test_quotes_are_exact_spans_and_durations_found():
    for s in sentences(ARTICLE):
        assert ARTICLE[s["field"]][s["start"]:s["end"]] == s["text"]
    d = duration_candidates({"headline": "", "summary": "Closed for at least 3 weeks; output halted for two days."})
    assert [(x["days"], x["is_lower_bound"]) for x in d] == [(21, True), (2, False)]


def _client(handler, retries=2):
    return JevClient(api_key="k", transport=httpx.MockTransport(handler), max_retries=retries, sleep=lambda s: None)


def test_401_diagnosed_without_retry():
    calls = []
    def h(req):
        calls.append(req)
        return httpx.Response(401, json={"error": "bad key"})
    with pytest.raises(JevError) as e:
        _client(h).decide({"model": "m", "state": {}, "questions": {}})
    assert e.value.code == "unauthorized" and not e.value.retryable and len(calls) == 1
    assert "TYPESAFE_API_KEY" in e.value.message


def test_429_and_529_bounded_retries():
    calls = []
    def h(req):
        calls.append(req)
        return httpx.Response(429 if len(calls) < 3 else 529, headers={"retry-after": "0"})
    with pytest.raises(JevError) as e:
        _client(h).decide({"model": "m", "state": {}, "questions": {}})
    assert len(calls) == 3 and e.value.retryable


def test_retry_then_success_and_bearer_header():
    calls = []
    def h(req):
        calls.append(req)
        if len(calls) == 1:
            return httpx.Response(529)
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {}, "usage": {"input_tokens": 1, "output_tokens": 1}})
    res = _client(h).decide({"model": "jev-1.13.0", "state": {}, "questions": {}})
    assert res.attempts == 2 and res.model == "jev-1.13.0"
    assert calls[0].headers["authorization"] == "Bearer k"
    assert str(calls[0].url) == "https://api.typesafe.ai/v1/systemone"


def test_missing_key_is_unconfigured():
    with pytest.raises(JevError) as e:
        JevClient(api_key="").decide({"model": "m", "state": {}, "questions": {}})
    assert e.value.code == "engine_not_configured"


def test_validation_rejects_missing_or_out_of_range():
    body = {"questions": {"a": {"type": "noul"}, "b": {"type": "choice", "criteria": {"x": "", "y": ""}},
                          "c": {"type": "score", "criteria": ["1", "2", "3"]}}}
    good = {"answers": {"a": {"type": "noul", "noul": 0.4}, "b": {"type": "choice", "choice": "x", "confidence": 0.7, "probabilities": {"x": 0.7, "y": 0.3}},
                        "c": {"type": "score", "score": 1.5, "confidence": 0.8}}}
    assert validate_answers(body, good)["c"]["score"] == 1.5
    for broken in [{"a": {"noul": 1.5}}, {"a": {"noul": True}}, {"b": {"choice": "z"}}, {"c": {"score": 3}}, {"a": None}]:
        bad = json.loads(json.dumps(good))
        for k, v in broken.items():
            if v is None:
                del bad["answers"][k]
            else:
                bad["answers"][k].update(v)
        with pytest.raises(InvalidJevResponse):
            validate_answers(body, bad)
