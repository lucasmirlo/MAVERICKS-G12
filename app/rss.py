"""Ingesta RSS/Atom real: ETag/Last-Modified, límites de tamaño y redirects, guardia SSRF y versiones por hash."""
from __future__ import annotations

import calendar
import ipaddress
import logging
import re
import socket
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import jobqueue
from .config import get_settings, rss_config
from .db import utcnow
from .models import CONTEXT_RSS, Article, ArticleVersion, Job, Source
from .textutil import content_hash, html_to_text, normalize_space

log = logging.getLogger("srr.rss")
MAX_REDIRECTS = 3
SOURCE_LEASE_SECONDS = 60


class FetchError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def seed_sources(db: Session) -> None:
    cfg = rss_config()
    for s in cfg["sources"]:
        row = db.get(Source, s["id"])
        if row is None:
            db.add(Source(id=s["id"], name=s["name"], url=s["url"], language=s.get("language", "en"), topic=s.get("topic"),
                          enabled=s.get("enabled", True), poll_seconds=get_settings().rss_poll_seconds or cfg["poll_seconds"]))
        else:
            row.name, row.url, row.language, row.topic = s["name"], s["url"], s.get("language", "en"), s.get("topic")
    db.commit()


def _public_host(host: str) -> None:
    if not host:
        raise FetchError("invalid_url", "URL sin host.")
    if host.lower() in {"localhost", "localhost.localdomain"} or host.lower().endswith((".local", ".internal", ".localhost")):
        raise FetchError("blocked_host", f"Destino no permitido: {host}.")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FetchError("dns_error", f"No se pudo resolver {host}.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise FetchError("blocked_host", f"{host} resuelve a una dirección no pública ({ip}).")


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise FetchError("invalid_url", "Solo se permiten URLs http(s).")
    if parts.username or parts.password:
        raise FetchError("invalid_url", "La URL no puede incluir credenciales.")
    _public_host(parts.hostname or "")


def fetch(url: str, *, etag: str | None, last_modified: str | None, transport: httpx.BaseTransport | None = None,
          resolve_check=check_url) -> tuple[int, bytes | None, dict]:
    cfg = rss_config()
    max_bytes = cfg["max_response_bytes"]
    headers = {"User-Agent": "SupplierRiskRadar/1.0 (+demo; RSS reader)", "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    current = url
    with httpx.Client(timeout=cfg["timeout_seconds"], follow_redirects=False, transport=transport) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            resolve_check(current)
            try:
                with client.stream("GET", current, headers=headers) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            raise FetchError("bad_redirect", "Redirect sin Location.", resp.status_code)
                        current = urljoin(current, location)
                        continue
                    meta = {"etag": resp.headers.get("etag"), "last_modified": resp.headers.get("last-modified"),
                            "final_url": current, "content_type": resp.headers.get("content-type")}
                    if resp.status_code == 304:
                        return 304, None, meta
                    if resp.status_code != 200:
                        raise FetchError("http_error", f"La fuente respondió HTTP {resp.status_code}.", resp.status_code)
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise FetchError("too_large", f"Respuesta de {int(declared)} bytes supera el límite de {max_bytes}.", 200)
                    chunks, size = [], 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise FetchError("too_large", f"La respuesta supera el límite de {max_bytes} bytes.", 200)
                        chunks.append(chunk)
                    return 200, b"".join(chunks), meta
            except httpx.TimeoutException as exc:
                raise FetchError("timeout", f"Tiempo de espera agotado ({cfg['timeout_seconds']} s).") from exc
            except httpx.TransportError as exc:
                raise FetchError("connection_error", f"Error de conexión ({exc.__class__.__name__}).") from exc
        raise FetchError("too_many_redirects", f"Más de {MAX_REDIRECTS} redirects.")


_ENTITY_DECL = re.compile(rb"<!ENTITY", re.I)


def parse(body: bytes) -> list[dict]:
    if _ENTITY_DECL.search(body[:20000]):
        raise FetchError("xml_entities_rejected", "El XML declara entidades; se rechaza por seguridad.")
    feed = feedparser.parse(body, sanitize_html=True, resolve_relative_uris=False)
    if feed.bozo and not feed.entries:
        raise FetchError("invalid_xml", f"XML no válido: {type(feed.bozo_exception).__name__}.")
    if not feed.entries and not feed.feed:
        raise FetchError("invalid_xml", "El documento no es RSS/Atom reconocible.")
    items = []
    for e in feed.entries:
        title = html_to_text(e.get("title"), 500)
        summary = html_to_text(e.get("summary") or e.get("description"), 3000)
        link = e.get("link")
        guid = e.get("id") or e.get("guid")
        parsed = e.get("published_parsed") or e.get("updated_parsed")
        published = datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc) if parsed else None
        geo = {}
        for k, v in e.items():
            if (k.startswith("geo_") or k.startswith("georss_") or k in {"gdacs_country", "gdacs_iso3", "gdacs_alertlevel",
                                                                          "gdacs_eventtype", "gdacs_severity"}) and isinstance(v, str):
                geo[k] = normalize_space(v)[:200]
        if title or summary:
            items.append({"title": title, "summary": summary, "link": link if _http(link) else None, "guid": guid,
                          "published_at": published, "geo": geo or None})
    return items


def _http(url) -> bool:
    return isinstance(url, str) and urlsplit(url).scheme in {"http", "https"}


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    # Se conservan query y path (pueden identificar el artículo); solo se normaliza esquema/host y fragmento.
    return urlunsplit((parts.scheme.lower(), (parts.hostname or "").lower() + (f":{parts.port}" if parts.port else ""), parts.path or "/", parts.query, ""))


def acquire_source(db: Session, source_id: str, owner: str) -> bool:
    got = db.execute(text("UPDATE sources SET lease_owner=:o, lease_until=now() + make_interval(secs => :s) "
                          "WHERE id=:id AND enabled AND (lease_until IS NULL OR lease_until < now()) RETURNING id"),
                     {"o": owner, "s": SOURCE_LEASE_SECONDS, "id": source_id}).scalar()
    db.commit()
    return bool(got)


def release_source(db: Session, source_id: str, owner: str) -> None:
    db.execute(text("UPDATE sources SET lease_owner=NULL, lease_until=NULL WHERE id=:id AND lease_owner=:o"), {"id": source_id, "o": owner})
    db.commit()


def budget_used_today(db: Session) -> int:
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count(Job.id)).where(Job.kind == "analyze_article", Job.priority == jobqueue.PRIORITY_RSS_ANALYSIS,
                                                      Job.created_at >= start, Job.error_code.is_distinct_from("budget_exceeded"))) or 0


def sync_source(db: Session, source_id: str, owner: str, *, transport: httpx.BaseTransport | None = None,
                resolve_check=check_url, now: datetime | None = None) -> dict:
    if not acquire_source(db, source_id, owner):
        return {"source_id": source_id, "outcome": "skipped_locked"}
    src = db.get(Source, source_id)
    cfg = rss_config()
    now = now or utcnow()
    started = time.monotonic()
    src.last_attempt_at = now
    db.commit()
    result = {"source_id": source_id, "new": 0, "versions": 0, "duplicates": 0, "too_old": 0, "deferred": 0, "items": 0}
    try:
        status, body, meta = fetch(src.url, etag=src.etag, last_modified=src.last_modified, transport=transport, resolve_check=resolve_check)
        src.last_status = status
        if status == 304:
            src.last_outcome = "not_modified"
            src.last_new_count = 0
        else:
            items = parse(body)
            result["items"] = len(items)
            src.last_item_count = len(items)
            _store_items(db, src, items, cfg, now, result)
            src.last_outcome = "ok"
            src.last_new_count = result["new"] + result["versions"]
            src.initial_done = True
        src.etag = meta.get("etag") or src.etag
        src.last_modified = meta.get("last_modified") or src.last_modified
        src.last_success_at = now
        src.consecutive_errors = 0
        src.error_message = None
        result["outcome"] = src.last_outcome
    except FetchError as exc:
        db.rollback()
        src = db.get(Source, source_id)
        src.last_outcome = "error"
        src.last_status = exc.status
        src.error_count = (src.error_count or 0) + 1
        src.consecutive_errors = (src.consecutive_errors or 0) + 1
        src.error_message = f"{exc.code}: {exc.message}"
        result.update(outcome="error", error=exc.code, message=exc.message)
        log.warning("rss source=%s error=%s %s", source_id, exc.code, exc.message)
    finally:
        src.last_duration_ms = int((time.monotonic() - started) * 1000)
        db.commit()
        release_source(db, source_id, owner)
    log.info("rss source=%s result=%s", source_id, result)
    return result


def _store_items(db: Session, src: Source, items: list[dict], cfg: dict, now: datetime, result: dict) -> None:
    lookback = now - timedelta(hours=cfg["initial_lookback_hours"])
    max_new = cfg["max_new_items_per_source_poll"]
    budget = get_settings().rss_daily_analysis_budget or cfg["daily_analysis_budget"]
    items = sorted(items, key=lambda i: i["published_at"] or now, reverse=True)
    for item in items:
        if item["published_at"] and item["published_at"] < lookback:
            result["too_old"] += 1
            continue
        if item["guid"]:
            identity = f"{src.id}:guid:{item['guid']}"[:600]
        elif item["link"]:
            identity = f"{src.id}:url:{canonical_url(item['link'])}"[:600]
        else:
            identity = f"{src.id}:hash:{content_hash(item['title'], item['summary'])}"
        h = content_hash(item["title"], item["summary"])
        article = db.scalar(select(Article).where(Article.context_id == CONTEXT_RSS, Article.identity_key == identity))
        if article is not None:
            if db.scalar(select(ArticleVersion.id).where(ArticleVersion.article_id == article.id, ArticleVersion.content_hash == h)):
                result["duplicates"] += 1
                continue
            n = (db.scalar(select(func.max(ArticleVersion.version)).where(ArticleVersion.article_id == article.id)) or 0) + 1
            version = ArticleVersion(article_id=article.id, version=n, headline=item["title"], summary=item["summary"], content_hash=h, fetched_at=now)
            db.add(version)
            db.flush()
            article.current_version_id = version.id
            article.url = item["link"] or article.url
            article.published_at = item["published_at"] or article.published_at
            result["versions"] += 1
        else:
            if result["new"] >= max_new:
                continue
            article = Article(context_id=CONTEXT_RSS, origin="rss", external_id=(item["guid"] or item["link"] or h)[:512],
                              identity_key=identity, source_id=src.id, source_name=src.name, url=item["link"],
                              language=src.language, published_at=item["published_at"],
                              published_raw=item["published_at"].isoformat() if item["published_at"] else None,
                              first_seen_at=now, geo=item["geo"])
            db.add(article)
            db.flush()
            version = ArticleVersion(article_id=article.id, version=1, headline=item["title"], summary=item["summary"], content_hash=h, fetched_at=now)
            db.add(version)
            db.flush()
            article.current_version_id = version.id
            result["new"] += 1
        over = budget_used_today(db) >= budget
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        jobqueue.enqueue(db, "analyze_article", {"version_id": version.id, "origin": "rss"},
                         priority=jobqueue.PRIORITY_RSS_ANALYSIS, idempotency_key=f"analyze:{version.id}",
                         run_at=tomorrow if over else None,
                         error_code="budget_exceeded" if over else None,
                         error_message=f"Cupo diario de {budget} análisis RSS alcanzado; en espera hasta {tomorrow.isoformat()}" if over else None)
        if over:
            result["deferred"] += 1
        db.flush()
