"""Importación de Excel por esquema. Lee en memoria, sin modificar el original ni ejecutar fórmulas."""
from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import date, datetime, timezone
from typing import Any

import openpyxl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import file_policy, get_settings
from .models import (
    CONTEXT_EXERCISE,
    Article,
    ArticleVersion,
    EvaluationLabel,
    ImportBatch,
    Material,
    MaterialProduct,
    Supplier,
)
from .textutil import content_hash, normalize_space

SUPPLIER_COLUMNS = [
    "Supplier_ID", "Supplier_Name", "Category", "Material_Supplied", "Country", "City", "Annual_Spend_EUR",
    "Share_of_Category_Spend_%", "Single_Source", "Approved_Alternate_ID", "Lead_Time_Days",
    "Inventory_Cover_Days", "Criticality", "Quality_Score",
]
MATERIAL_REQUIRED = ["Material_ID", "Material", "Primary_Supplier_ID", "Used_In_Products"]
NEWS_REQUIRED = ["News_ID", "Published_Date", "Headline", "Summary"]
# Columnas que nunca llegan al contexto de inferencia.
LABEL_COLUMNS = ["Is_Risk", "Urgent", "Affected_Supplier_IDs", "Event_Type", "Explanation"]
SHEET_SPLITS = {"News": "training", "News_Train": "training", "News_Validation": "validation", "News_Test": "test", "News_Feed": "liveday"}
SPLIT_LABELS = {"training": "Entrenamiento", "validation": "Validación", "test": "Test", "liveday": "LiveDay", "other": "Otro"}


class ImportFailure(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _validate_container(data: bytes, filename: str) -> None:
    settings = get_settings()
    lower = filename.lower()
    if lower.endswith((".xlsm", ".xlsb", ".xltm")):
        raise ImportFailure("macro_format", "Los formatos con macros no están permitidos. Guarda el archivo como .xlsx.")
    if not lower.endswith(".xlsx"):
        raise ImportFailure("unsupported_format", "Solo se admiten archivos .xlsx.")
    if len(data) > settings.import_max_bytes:
        raise ImportFailure("file_too_large", f"El archivo supera el límite de {settings.import_max_bytes // (1024 * 1024)} MB.")
    if not data.startswith(b"PK\x03\x04"):
        raise ImportFailure("corrupt_file", "El archivo está dañado o no es un libro .xlsx válido.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                raise ImportFailure("macro_format", "El libro contiene macros (vbaProject.bin) y no se importa.")
            content_types = zf.read("[Content_Types].xml").decode("utf-8", "replace")
            if "macroEnabled" in content_types:
                raise ImportFailure("macro_format", "El libro está declarado con macros y no se importa.")
    except zipfile.BadZipFile as exc:
        raise ImportFailure("corrupt_file", "El archivo está dañado o no es un libro .xlsx válido.") from exc
    except KeyError as exc:
        raise ImportFailure("corrupt_file", "Falta [Content_Types].xml; el libro no es un .xlsx válido.") from exc


def _rows(ws) -> tuple[list[str], list[tuple]]:
    rows = list(ws.iter_rows(values_only=True))
    while rows and all(v is None for v in rows[-1]):
        rows.pop()
    if not rows:
        return [], []
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    while header and header[-1] == "":
        header.pop()
    body = [tuple(r[: len(header)]) for r in rows[1:] if any(v is not None and str(v).strip() != "" for v in r)]
    return header, body


def _cell_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = normalize_space(str(value))
    return text or None


def _cell_number(value, field: str, issues: list[str]) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        issues.append(f"{field}: valor no numérico")
        return None
    try:
        number = float(str(value).replace(",", ".")) if isinstance(value, str) else float(value)
    except ValueError:
        issues.append(f"{field}: valor no numérico '{value}'")
        return None
    if number != number or number in (float("inf"), float("-inf")):
        issues.append(f"{field}: valor no finito")
        return None
    return number


def parse_date(value) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc), value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc), value.isoformat()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc), text
        except ValueError:
            continue
    return None, text


def _split_ids(value) -> list[str]:
    text = _cell_text(value)
    if not text:
        return []
    parts = [p.strip() for p in text.replace(",", ";").split(";")]
    return sorted({p for p in parts if p})


def detect_news_split(sheet_name: str, header: list[str]) -> str:
    if sheet_name in SHEET_SPLITS:
        return SHEET_SPLITS[sheet_name]
    # Hoja con nombre no estándar: se decide por el esquema de columnas.
    cols = set(header)
    if {"Event_Type", "Explanation"} <= cols:
        return "other"
    if "Is_Risk" in cols:
        return "test"
    return "liveday"


def classify_sheet(name: str, header: list[str]) -> str | None:
    cols = set(header)
    if set(SUPPLIER_COLUMNS) <= cols:
        return "suppliers"
    if set(MATERIAL_REQUIRED) <= cols:
        return "materials"
    if set(NEWS_REQUIRED) <= cols:
        return "news"
    return None


def import_workbook(db: Session, data: bytes, filename: str, context_id: str = CONTEXT_EXERCISE) -> dict:
    _validate_container(data, filename)
    sha = hashlib.sha256(data).hexdigest()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl lanza varios tipos
        raise ImportFailure("corrupt_file", "No se pudo leer el libro .xlsx; puede estar dañado.") from exc

    sheets: dict[str, tuple[str, list[str], list[tuple]]] = {}
    recognition = []
    for ws in wb.worksheets:
        header, body = _rows(ws)
        kind = classify_sheet(ws.title, header)
        recognition.append({"sheet": ws.title, "recognized_as": kind, "rows": len(body), "columns": header})
        if kind:
            if len(body) > get_settings().import_max_rows:
                raise ImportFailure("too_many_rows", f"La hoja {ws.title} tiene {len(body)} filas; el límite es {get_settings().import_max_rows}.")
            sheets[ws.title] = (kind, header, body)
    wb.close()

    if not sheets:
        expected = "Suppliers (" + ", ".join(SUPPLIER_COLUMNS[:3]) + "…) o noticias (" + ", ".join(NEWS_REQUIRED) + ")"
        raise ImportFailure("no_known_sheet", f"Ninguna hoja tiene las columnas mínimas esperadas: {expected}.", recognition)

    results = []
    kinds = {k for k, _, _ in sheets.values()}
    if "materials" in kinds and "suppliers" not in kinds and db.scalar(select(Supplier).limit(1)) is None:
        raise ImportFailure("catalog_incomplete", "La hoja Materials necesita importar antes Suppliers.")
    supplier_sheet = next((n for n, (k, _, _) in sheets.items() if k == "suppliers"), None)
    if supplier_sheet:
        material_sheet = next((n for n, (k, _, _) in sheets.items() if k == "materials"), None)
        results.append(_import_catalog(db, sha, filename, supplier_sheet, sheets[supplier_sheet], material_sheet,
                                       sheets.get(material_sheet) if material_sheet else None))
    for name, (kind, header, body) in sheets.items():
        if kind == "news":
            results.append(_import_news(db, sha, filename, name, header, body, context_id))
    db.commit()
    return {"file_sha256": sha, "file_name": filename, "sheets": recognition, "batches": results}


def _import_catalog(db: Session, sha, filename, s_name, s_sheet, m_name, m_sheet) -> dict:
    existing = db.scalar(select(ImportBatch).where(ImportBatch.file_sha256 == sha, ImportBatch.sheet_name == s_name, ImportBatch.kind == "catalog"))
    if existing and db.scalar(select(Supplier).limit(1)) is not None:
        return {"batch_id": existing.id, "kind": "catalog", "sheet": s_name, "status": "already_imported",
                "rows": existing.row_count, "diagnostics": existing.diagnostics}
    policy = file_policy()
    _, header, body = s_sheet
    idx = {h: i for i, h in enumerate(header)}
    diagnostics: list[dict] = []
    ids = [_cell_text(r[idx["Supplier_ID"]]) for r in body]
    dupes = sorted({i for i in ids if i and ids.count(i) > 1})
    if dupes or any(i is None for i in ids):
        raise ImportFailure("invalid_supplier_ids", "Supplier_ID vacío o repetido en Suppliers.", {"duplicates": dupes})
    batch = existing or ImportBatch(kind="catalog", split=None, file_name=filename, sheet_name=s_name, file_sha256=sha)
    batch.columns = header
    batch.row_count = len(body)
    if not existing:
        db.add(batch)
        db.flush()
    suppliers = []
    id_set = set(ids)
    for n, r in enumerate(body):
        def get(col):
            return r[idx[col]] if col in idx else None
        issues: list[str] = []
        sid = _cell_text(get("Supplier_ID"))
        category = _cell_text(get("Category"))
        criticality = _cell_text(get("Criticality"))
        single = _cell_text(get("Single_Source"))
        share = _cell_number(get("Share_of_Category_Spend_%"), "Share_of_Category_Spend_%", issues)
        lead = _cell_number(get("Lead_Time_Days"), "Lead_Time_Days", issues)
        inv = _cell_number(get("Inventory_Cover_Days"), "Inventory_Cover_Days", issues)
        spend = _cell_number(get("Annual_Spend_EUR"), "Annual_Spend_EUR", issues)
        quality = _cell_number(get("Quality_Score"), "Quality_Score", issues)
        alt = _cell_text(get("Approved_Alternate_ID"))
        if share is not None and not 0 <= share <= 100:
            issues.append("Share_of_Category_Spend_%: fuera de 0–100")
        for field, v in (("Lead_Time_Days", lead), ("Inventory_Cover_Days", inv), ("Annual_Spend_EUR", spend)):
            if v is not None and v < 0:
                issues.append(f"{field}: valor negativo")
        if lead == 0:
            issues.append("Lead_Time_Days: cero no es un plazo válido")
        if criticality is not None and criticality not in policy["criticality"]:
            issues.append(f"Criticality: categoría desconocida '{criticality}'")
        if single is not None and single not in {"Y", "N"}:
            issues.append(f"Single_Source: valor desconocido '{single}'")
        if category in policy["buffer_not_applicable_categories"] and inv is not None:
            issues.append("Inventory_Cover_Days: informado en una categoría sin inventario aplicable")
        if alt and alt not in id_set:
            issues.append(f"Approved_Alternate_ID: {alt} no existe en la cartera")
        if issues:
            diagnostics.append({"level": "warning", "row": n + 2, "supplier_id": sid, "issues": issues})
        suppliers.append(Supplier(
            supplier_id=sid, name=_cell_text(get("Supplier_Name")) or sid, category=category,
            material=_cell_text(get("Material_Supplied")), country=_cell_text(get("Country")), city=_cell_text(get("City")),
            annual_spend_eur=spend, share_category_pct=share, single_source=single, alternate_id=alt,
            lead_days=lead, inventory_days=inv, criticality=criticality, quality_score=quality, row_index=n,
            data_issues=issues, catalog_batch_id=batch.id,
        ))
    for s in suppliers:
        db.merge(s)
    materials_count = products_count = 0
    if m_sheet:
        _, mh, mb = m_sheet
        midx = {h: i for i, h in enumerate(mh)}
        db.execute(delete(MaterialProduct))
        db.execute(delete(Material))
        products = set()
        for n, r in enumerate(mb):
            def mget(col):
                return r[midx[col]] if col in midx else None
            mid = _cell_text(mget("Material_ID"))
            if not mid:
                diagnostics.append({"level": "warning", "row": n + 2, "issues": ["Material_ID vacío; fila omitida"]})
                continue
            m_issues: list[str] = []
            primary = _cell_text(mget("Primary_Supplier_ID"))
            alt = _cell_text(mget("Alternate_Supplier_ID"))
            for field, v in (("Primary_Supplier_ID", primary), ("Alternate_Supplier_ID", alt)):
                if v and v not in id_set:
                    m_issues.append(f"{field}: {v} no existe en Suppliers")
            qty = _cell_number(mget("Monthly_Requirement"), "Monthly_Requirement", m_issues)
            if m_issues:
                diagnostics.append({"level": "warning", "row": n + 2, "material_id": mid, "issues": m_issues})
            db.add(Material(material_id=mid, name=_cell_text(mget("Material")) or mid, category=_cell_text(mget("Category")),
                            primary_supplier_id=primary, alternate_supplier_id=alt, monthly_requirement=qty,
                            unit=_cell_text(mget("Unit")), row_index=n))
            db.flush()
            raw_products = _cell_text(mget("Used_In_Products")) or ""
            for p in {normalize_space(p) for p in raw_products.replace(";", ",").split(",")}:
                if p:
                    products.add(p)
                    db.add(MaterialProduct(material_id=mid, product=p))
            materials_count += 1
        products_count = len(products)
    batch.diagnostics = diagnostics
    db.flush()
    return {"batch_id": batch.id, "kind": "catalog", "sheet": s_name, "materials_sheet": m_name, "status": "created",
            "rows": len(body), "suppliers": len(suppliers), "materials": materials_count, "products": products_count,
            "diagnostics": diagnostics}


def _import_news(db: Session, sha, filename, sheet, header, body, context_id) -> dict:
    existing = db.scalar(select(ImportBatch).where(ImportBatch.file_sha256 == sha, ImportBatch.sheet_name == sheet,
                                                   ImportBatch.context_id == context_id))
    if existing:
        return {"batch_id": existing.id, "kind": "news", "split": existing.split, "sheet": sheet,
                "status": "already_imported", "rows": existing.row_count, "has_labels": existing.has_labels,
                "diagnostics": existing.diagnostics}
    idx = {h: i for i, h in enumerate(header)}
    split = detect_news_split(sheet, header)
    ids = [_cell_text(r[idx["News_ID"]]) for r in body]
    dupes = sorted({i for i in ids if i and ids.count(i) > 1})
    missing = [n + 2 for n, i in enumerate(ids) if not i]
    if dupes or missing:
        raise ImportFailure("invalid_news_ids", f"News_ID vacío o repetido en {sheet}.", {"duplicates": dupes, "rows_without_id": missing})
    input_columns = [h for h in header if h and h not in LABEL_COLUMNS]
    label_columns = [h for h in header if h in LABEL_COLUMNS]
    batch = ImportBatch(kind="news", split=split, context_id=context_id, file_name=filename, sheet_name=sheet,
                        file_sha256=sha, columns=header, row_count=len(body))
    db.add(batch)
    db.flush()
    diagnostics = []
    has_labels = False
    max_date = None
    for n, r in enumerate(body):
        def get(col):
            return r[idx[col]] if col in idx else None
        news_id = ids[n]
        headline = _cell_text(get("Headline")) or ""
        summary = _cell_text(get("Summary")) or ""
        published_at, published_raw = parse_date(get("Published_Date"))
        if published_at is None:
            diagnostics.append({"level": "warning", "row": n + 2, "news_id": news_id, "issues": ["Published_Date no reconocida"]})
        elif max_date is None or published_at > max_date:
            max_date = published_at
        if not headline:
            diagnostics.append({"level": "warning", "row": n + 2, "news_id": news_id, "issues": ["Headline vacío"]})
        source_row = {}
        for col in input_columns:
            v = get(col)
            source_row[col] = v.isoformat() if isinstance(v, (datetime, date)) else _cell_text(v)
        article = Article(context_id=context_id, origin="excel", batch_id=batch.id, row_index=n, external_id=news_id,
                          identity_key=f"batch:{batch.id}:{news_id}", source_name=_cell_text(get("Source")),
                          language="en", published_at=published_at, published_raw=published_raw, source_row=source_row)
        db.add(article)
        db.flush()
        version = ArticleVersion(article_id=article.id, version=1, headline=headline, summary=summary,
                                 content_hash=content_hash(headline, summary))
        db.add(version)
        db.flush()
        article.current_version_id = version.id
        labels = {c: get(c) for c in label_columns}
        if any(_cell_text(v) for v in labels.values()):
            has_labels = True
            db.add(EvaluationLabel(batch_id=batch.id, news_id=news_id, is_risk=_cell_text(labels.get("Is_Risk")),
                                   urgent=_cell_text(labels.get("Urgent")),
                                   affected_supplier_ids=_split_ids(labels.get("Affected_Supplier_IDs")),
                                   event_type=_cell_text(labels.get("Event_Type")),
                                   explanation=_cell_text(labels.get("Explanation"))))
    batch.has_labels = has_labels
    batch.logical_date = max_date
    batch.diagnostics = diagnostics
    db.flush()
    return {"batch_id": batch.id, "kind": "news", "split": split, "sheet": sheet, "status": "created", "rows": len(body),
            "has_labels": has_labels, "label_columns_separated": label_columns, "diagnostics": diagnostics}
