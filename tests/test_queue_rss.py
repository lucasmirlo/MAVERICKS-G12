"""Cola con dos reclamadores, recuperación de lease e ingesta RSS (304, duplicado, edición, XML inválido, caída aislada)."""
import threading
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select, text

from app import jobqueue, rss
from app.db import SessionLocal
from app.models import Article, ArticleVersion, Job, Source

NOW = datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)


def test_two_claimers_never_share_a_job(db):
    for n in range(20):
        jobqueue.enqueue(db, "noop", {"n": n}, idempotency_key=f"k{n}")
    db.commit()
    claimed: list[str] = []
    lock = threading.Lock()

    def worker(name):
        while True:
            with SessionLocal() as s:
                job = jobqueue.claim(s, name)
            if job is None:
                return
            with lock:
                claimed.append(job.id)
            with SessionLocal() as s:
                jobqueue.complete(s, job.id, name)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(claimed) == 20 and len(set(claimed)) == 20


def test_priority_manual_batch_before_rss(db):
    jobqueue.enqueue(db, "analyze_article", {}, priority=jobqueue.PRIORITY_RSS_ANALYSIS, idempotency_key="rss")
    jobqueue.enqueue(db, "analyze_article", {}, priority=jobqueue.PRIORITY_MANUAL_BATCH, idempotency_key="manual")
    db.commit()
    assert jobqueue.claim(db, "w").idempotency_key == "manual"


def test_idempotent_enqueue(db):
    a, new_a = jobqueue.enqueue(db, "x", {}, idempotency_key="same")
    b, new_b = jobqueue.enqueue(db, "x", {}, idempotency_key="same")
    assert a == b and new_a and not new_b


def test_expired_lease_is_recovered(db):
    jid, _ = jobqueue.enqueue(db, "x", {}, idempotency_key="lease")
    db.commit()
    job = jobqueue.claim(db, "dead-worker")
    db.execute(text("UPDATE jobs SET lease_until = now() - interval '1 second' WHERE id=:id"), {"id": jid})
    db.commit()
    again = jobqueue.claim(db, "new-worker")
    assert again is not None and again.id == jid and again.attempts == 2 and again.lease_owner == "new-worker"
    # Sin intentos restantes pasa a failed
    db.execute(text("UPDATE jobs SET lease_until = now() - interval '1 second', attempts=max_attempts WHERE id=:id"), {"id": jid})
    db.commit()
    assert jobqueue.recover_expired(db) == 1
    db.expire_all()
    assert db.get(Job, jid).status == "failed"


def test_retryable_failure_backoff(db):
    jid, _ = jobqueue.enqueue(db, "x", {}, idempotency_key="retry")
    db.commit()
    jobqueue.claim(db, "w")
    assert jobqueue.fail(db, jid, "w", code="rate_limited", message="429", retryable=True) == "retry"
    db.expire_all()
    job = db.get(Job, jid)
    assert job.status == "queued" and job.next_attempt_at > datetime.now(timezone.utc)


def feed(items, etag='"v1"'):
    entries = "".join(f"<item><title>{t}</title><description>{d}</description><link>https://example.com/{g}</link><guid>{g}</guid>"
                      f"<pubDate>Sun, 18 Oct 2026 08:00:00 GMT</pubDate></item>" for g, t, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>{entries}</channel></rss>'.encode(), etag


class FeedServer:
    def __init__(self):
        self.body, self.etag = feed([("g1", "Port strike", "Rotterdam port halted."), ("g2", "Fire &amp; smoke", "<b>Bold</b> text")])
        self.status = 200
        self.requests = []

    def __call__(self, request: httpx.Request):
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status)
        if request.headers.get("if-none-match") == self.etag:
            return httpx.Response(304)
        return httpx.Response(200, content=self.body, headers={"etag": self.etag, "content-type": "application/rss+xml"})


def _source(db, sid="s1"):
    db.add(Source(id=sid, name=sid, url=f"https://feeds.example.com/{sid}", language="en", enabled=True, poll_seconds=300))
    db.commit()


def sync(db, server, sid="s1"):
    return rss.sync_source(db, sid, "test", transport=httpx.MockTransport(server), resolve_check=lambda url: None, now=NOW)


def test_rss_new_duplicate_304_and_version(db):
    _source(db)
    server = FeedServer()
    r1 = sync(db, server)
    assert r1["new"] == 2 and r1["outcome"] == "ok"
    v = db.scalar(select(ArticleVersion).join(Article).where(Article.external_id == "g2"))
    assert v.summary == "Bold text" and v.headline == "Fire & smoke"  # HTML saneado
    jobs1 = db.scalar(select(func.count(Job.id)))
    r2 = sync(db, server)  # mismo ETag → 304
    assert r2["outcome"] == "not_modified" and server.requests[-1].headers["if-none-match"] == '"v1"'
    server.etag = '"v2"'
    r3 = sync(db, server)  # contenido igual, ETag nuevo → duplicados sin análisis nuevo
    assert r3["duplicates"] == 2 and r3["new"] == 0 and db.scalar(select(func.count(Job.id))) == jobs1
    server.body, server.etag = feed([("g1", "Port strike extended", "Rotterdam port halted for 5 days."), ("g2", "Fire &amp; smoke", "<b>Bold</b> text")], '"v3"')
    r4 = sync(db, server)
    assert r4["versions"] == 1
    art = db.scalar(select(Article).where(Article.external_id == "g1"))
    assert len(art.versions) == 2 and db.scalar(select(func.count(Article.id))) == 2
    assert db.scalar(select(func.count(Job.id))) == jobs1 + 1
    src = db.get(Source, "s1")
    assert src.last_success_at is not None and src.last_outcome == "ok"


def test_rss_failure_is_visible_and_isolated(db):
    _source(db, "down")
    _source(db, "up")
    bad = FeedServer()
    bad.status = 503
    good = FeedServer()
    assert sync(db, bad, "down")["outcome"] == "error"
    assert sync(db, good, "up")["outcome"] == "ok"
    down = db.get(Source, "down")
    assert down.last_outcome == "error" and "503" in down.error_message and down.last_success_at is None


def test_invalid_xml_and_entities_rejected(db):
    _source(db)
    server = FeedServer()
    server.body = b"<html><body>not a feed"
    assert sync(db, server)["outcome"] == "error"
    server.body = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss><channel><item><title>&x;</title></item></channel></rss>'
    server.etag = '"e"'
    res = sync(db, server)
    assert res["outcome"] == "error" and res["error"] == "xml_entities_rejected"


def test_old_items_skipped_and_cap(db):
    _source(db)
    server = FeedServer()
    old = [("o", "Old", "x")]
    body = feed(old)[0].replace(b"Sun, 18 Oct 2026", b"Mon, 12 Oct 2026")
    server.body = body
    assert sync(db, server)["too_old"] == 1


@pytest.mark.parametrize("url", ["http://localhost/feed", "http://127.0.0.1/x", "http://10.0.0.5/x", "file:///etc/passwd", "http://user:pw@example.com/"])
def test_ssrf_guard(url):
    with pytest.raises(rss.FetchError):
        rss.check_url(url)


def test_budget_defers_without_dropping(db, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "rss_daily_analysis_budget", 1)
    _source(db)
    sync(db, FeedServer())
    deferred = list(db.scalars(select(Job).where(Job.error_code == "budget_exceeded")))
    assert len(deferred) == 1 and deferred[0].status == "queued" and deferred[0].next_attempt_at > NOW
