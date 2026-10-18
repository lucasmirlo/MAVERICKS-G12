"""API: acceso público de lectura, mutaciones protegidas, CSRF, ausencia de etiquetas; importación de los cuatro esquemas."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.importer import ImportFailure, import_workbook
from app.main import app
from app.models import EvaluationLabel, ImportBatch


@pytest.fixture()
def client(db):
    return TestClient(app)


def login(client):
    r = client.post("/api/session", json={"password": "test-presenter-password"})
    assert r.status_code == 200
    return r.json()["csrf"]


def test_four_schemas_recognized(db):
    expected = {"supplier_training.xlsx": "training", "supplier_validation.xlsx": "validation", "supplier_test.xlsx": "test",
                "supplier_liveday.xlsx": "liveday"}
    for f, split in expected.items():
        res = import_workbook(db, open(f"inputs/{f}", "rb").read(), f)
        news = [b for b in res["batches"] if b["kind"] == "news"]
        assert len(news) == 1 and news[0]["split"] == split
    rows = {b.split: b.row_count for b in db.scalars(select(ImportBatch).where(ImportBatch.kind == "news"))}
    assert rows == {"training": 30, "validation": 10, "test": 20, "liveday": 14}
    test_batch = db.scalar(select(ImportBatch).where(ImportBatch.split == "test"))
    assert not test_batch.has_labels  # test sin respuestas: no hay etiquetas que evaluar
    assert db.scalar(select(EvaluationLabel).where(EvaluationLabel.batch_id == test_batch.id)) is None


def test_rejects_macro_corrupt_and_unknown(db):
    with pytest.raises(ImportFailure) as e:
        import_workbook(db, b"PK\x03\x04junk", "x.xlsm")
    assert e.value.code == "macro_format"
    with pytest.raises(ImportFailure) as e:
        import_workbook(db, b"not a zip", "x.xlsx")
    assert e.value.code == "corrupt_file"
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.append(["Foo", "Bar"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ImportFailure) as e:
        import_workbook(db, buf.getvalue(), "x.xlsx")
    assert e.value.code == "no_known_sheet"
    # vbaProject.bin dentro de un .xlsx renombrado
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/vbaProject.bin", b"x")
    with pytest.raises(ImportFailure) as e:
        import_workbook(db, data.getvalue(), "x.xlsx")
    assert e.value.code == "macro_format"


def test_mutations_require_presenter_and_csrf(client):
    for method, path in [("post", "/api/imports"), ("post", "/api/batches/x/analyze"), ("post", "/api/sources/sync"),
                         ("put", "/api/policy"), ("post", "/api/drafts"), ("post", "/api/alerts/x/ack"),
                         ("post", "/api/incidents/x/resolve"), ("post", "/api/evaluations/x"), ("post", "/api/engine/test")]:
        r = getattr(client, method)(path, json={})
        assert r.status_code == 401, (path, r.status_code)
        assert r.json()["code"] == "presenter_required"
    login(client)
    r = client.post("/api/sources/sync")
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"


def test_login_rate_limited(client):
    from app import security
    security._attempts.clear()
    for _ in range(5):
        assert client.post("/api/session", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/session", json={"password": "wrong"}).status_code == 429
    security._attempts.clear()


def test_public_reads_and_no_labels(client, db):
    from app import security
    security._attempts.clear()
    csrf = login(client)
    data = open("inputs/supplier_training.xlsx", "rb").read()
    r = client.post("/api/imports", files={"file": ("supplier_training.xlsx", data)}, headers={"x-csrf-token": csrf})
    assert r.status_code == 200, r.text
    client.delete("/api/session")
    labels = list(db.scalars(select(EvaluationLabel)))
    anon = TestClient(app)
    payloads = []
    for path in ["/api/meta", "/api/overview", "/api/suppliers", "/api/articles?page_size=100", "/api/batches", "/api/alerts", "/api/sources",
                 "/api/suppliers/S001"]:
        resp = anon.get(path)
        assert resp.status_code == 200, (path, resp.text)
        payloads.append(resp.text)
    art_ids = [a["id"] for a in anon.get("/api/articles?page_size=100").json()["items"]]
    payloads += [anon.get(f"/api/articles/{i}").text for i in art_ids]
    blob = "\n".join(payloads)
    for lab in labels:
        assert lab.explanation not in blob
    assert "Explanation" not in blob and "Is_Risk" not in blob
    assert anon.get("/api/evaluations").status_code == 401
    sup = anon.get("/api/suppliers?page_size=100").json()
    assert sup["total"] == 40 and sum(1 for s in sup["items"] if not s["products_mapped"]) == 10
    meta = anon.get("/api/meta").json()
    assert "missing_variable" not in meta["engine"] and "test-key" not in json.dumps(meta)


def test_export_blocked_before_analysis(client, db):
    res = import_workbook(db, open("inputs/supplier_liveday.xlsx", "rb").read(), "supplier_liveday.xlsx")
    bid = res["batches"][0]["batch_id"]
    r = client.get(f"/api/batches/{bid}/export.xlsx")
    assert r.status_code == 409 and r.json()["code"] == "export_blocked" and len(r.json()["details"]["blockers"]) == 14


def test_health_and_ready(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json()["status"] == "ready"
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_reset_batch_removes_results_and_cache(client, db):
    from app import security
    from app.models import Analysis, Article, JevCall
    from app.pipeline import analyze_version
    from .helpers import ScriptedJev
    security._attempts.clear()
    res = import_workbook(db, open("inputs/supplier_training.xlsx", "rb").read(), "supplier_training.xlsx")
    bid = next(b for b in res["batches"] if b["kind"] == "news")["batch_id"]
    art = db.scalar(select(Article).where(Article.batch_id == bid).order_by(Article.row_index))
    analyze_version(db, art.current_version_id, client=ScriptedJev({}, event_type="other", event_state="unclear").client())
    assert db.scalar(select(JevCall)) is not None
    csrf = login(client)
    r = client.post(f"/api/batches/{bid}/reset", headers={"x-csrf-token": csrf})
    assert r.status_code == 200 and r.json()["analyses_deleted"] == 1
    db.expire_all()
    assert db.scalar(select(Analysis)) is None and db.scalar(select(JevCall)) is None
    assert db.scalar(select(Article).where(Article.batch_id == bid)) is not None  # las filas importadas se conservan


def test_draft_flow(client, db):
    from app import security
    security._attempts.clear()
    import_workbook(db, open("inputs/supplier_training.xlsx", "rb").read(), "supplier_training.xlsx")
    csrf = login(client)
    h = {"x-csrf-token": csrf}
    r = client.post("/api/drafts", json={"kind": "supplier", "supplier_id": "S001"}, headers=h)
    assert r.status_code == 200 and "Sunrise BioChem Ltd" in r.json()["body"] and r.json()["recipient"] is None
    r2 = client.post("/api/drafts", json={"kind": "alternate", "supplier_id": "S001"}, headers=h)
    assert r2.status_code == 200 and "Kaveri Fine Chemicals" in r2.json()["body"]
    assert "stock" not in r2.json()["body"].lower() or "sin confirmar" in r2.json()["body"].lower()
    r3 = client.post("/api/drafts", json={"kind": "alternate", "supplier_id": "S003"}, headers=h)
    assert r3.status_code == 409 and r3.json()["code"] == "no_alternate"
    p = client.patch(f"/api/drafts/{r.json()['id']}", json={"body": "Texto editado"}, headers=h)
    assert p.json()["body"] == "Texto editado" and p.json()["edited"]
