"""Versiones de política. La inicial procede exactamente de config/risk_policy.json."""
from __future__ import annotations

import copy
import math

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import file_policy
from .models import PolicyVersion

EDITABLE_THRESHOLDS = ("link", "risk", "urgent", "review_low", "review_high", "choice_score_confidence", "audible_probability")


def ensure_seeded(db: Session) -> None:
    """El archivo config/risk_policy.json manda: una versión nueva del archivo se registra y pasa a ser la activa."""
    base = file_policy()
    if db.get(PolicyVersion, base["version"]) is None:
        db.execute(update(PolicyVersion).values(active=False))
        db.add(PolicyVersion(version=base["version"], data=base, active=True, note=f"Política del archivo {base['version']}"))
        db.commit()


def active_policy(db: Session) -> dict:
    row = db.scalar(select(PolicyVersion).where(PolicyVersion.active.is_(True)).limit(1))
    if row is None:
        ensure_seeded(db)
        row = db.scalar(select(PolicyVersion).where(PolicyVersion.active.is_(True)).limit(1))
    return row.data if row else file_policy()


def get_policy(db: Session, version: str) -> dict | None:
    row = db.get(PolicyVersion, version)
    return row.data if row else None


def validate_policy(data: dict) -> list[str]:
    errors = []
    weights = data.get("weights", {})
    if set(weights) != {"C", "U", "B", "G"}:
        errors.append("weights debe contener C, U, B y G")
    elif any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in weights.values()):
        errors.append("los pesos deben ser números no negativos")
    elif abs(sum(weights.values()) - 1) > 1e-9:
        errors.append("los pesos deben sumar 1")
    t = data.get("thresholds", {})
    for key in EDITABLE_THRESHOLDS:
        v = t.get(key)
        if not isinstance(v, (int, float)) or not 0 <= v <= 1:
            errors.append(f"umbral {key} debe estar entre 0 y 1")
    if not errors and not t["review_low"] <= t["review_high"]:
        errors.append("review_low debe ser menor o igual que review_high")
    return errors


def create_version(db: Session, *, base_version: str, changes: dict, note: str) -> PolicyVersion:
    base = get_policy(db, base_version)
    if base is None:
        raise ValueError("versión base desconocida")
    data = copy.deepcopy(base)
    if "weights" in changes:
        data["weights"] = {k: float(changes["weights"][k]) for k in ("C", "U", "B", "G")}
    for key, value in (changes.get("thresholds") or {}).items():
        if key in EDITABLE_THRESHOLDS:
            data["thresholds"][key] = float(value)
    errors = validate_policy(data)
    if errors:
        raise ValueError("; ".join(errors))
    n = 1
    while db.get(PolicyVersion, f"{base['version'].split('+')[0]}+p{n}") is not None:
        n += 1
    data["version"] = f"{base['version'].split('+')[0]}+p{n}"
    data["status"] = "presenter_modified_not_calibrated"
    db.execute(update(PolicyVersion).values(active=False))
    row = PolicyVersion(version=data["version"], data=data, active=True, note=note)
    db.add(row)
    db.commit()
    return row


def activate(db: Session, version: str) -> None:
    if db.get(PolicyVersion, version) is None:
        raise ValueError("versión desconocida")
    db.execute(update(PolicyVersion).values(active=False))
    db.execute(update(PolicyVersion).where(PolicyVersion.version == version).values(active=True))
    db.commit()
