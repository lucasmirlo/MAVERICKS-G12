"""Voto por mayoría de scripts/export_consensus.py."""
import importlib.util

from app.config import ROOT

spec = importlib.util.spec_from_file_location("export_consensus", ROOT / "scripts" / "export_consensus.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run(*rows):
    return {"rows": [{"news_id": n, "is_risk": r, "urgent": u, "affected": a} for n, r, u, a in rows]}


def test_majority_vote_per_flag_and_id():
    runs = [run(("T1", "Y", "Y", ["S1", "S2"]), ("T2", "N", "N", [])),
            run(("T1", "Y", "N", ["S1"]), ("T2", "Y", "Y", ["S3"])),
            run(("T1", "Y", "Y", ["S1", "S4"]), ("T2", "N", "N", ["S3"]))]
    v = mod.vote(runs)
    assert v[0]["is_risk"] == "Y" and v[0]["urgent"] == "Y" and v[0]["affected"] == ["S1"] and not v[0]["unanimous"]
    # Riesgo N por mayoría fuerza Urgent N aunque un voto fuese urgente; S3 aparece 2 de 3 veces.
    assert v[1]["is_risk"] == "N" and v[1]["urgent"] == "N" and v[1]["affected"] == ["S3"]


def test_unanimous_rows():
    runs = [run(("T1", "N", "N", ["S9"]))] * 3
    assert mod.vote(runs)[0]["unanimous"]
