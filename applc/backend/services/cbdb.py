from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from backend.db import db, json_dumps, utc_now
from backend.services.normalization import compact_text, to_traditional

CBDB_PERSON_API = "https://cbdb.fas.harvard.edu/cbdbapi/person.php"


def update_cbdb_people(names: list[str] | None = None, include_extracted: bool = False, include_terms: bool = False) -> dict[str, Any]:
    candidates = _collect_names(names or [], include_extracted, include_terms)
    summary = {"requested": len(candidates), "imported": 0, "skipped": 0, "no_results": [], "errors": []}
    for name in candidates:
        try:
            records = fetch_cbdb_person(name)
        except Exception as exc:
            summary["errors"].append({"name": name, "error": str(exc)})
            continue
        if not records:
            summary["no_results"].append(name)
            continue
        result = import_cbdb_records(records, fallback_name=name)
        summary["imported"] += result["imported"]
        summary["skipped"] += result["skipped"]
        summary["errors"].extend(result["errors"])
    return summary


def fetch_cbdb_person(name: str, timeout: int = 20) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"name": name, "o": "json"})
    url = f"{CBDB_PERSON_API}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "MingShiluResearchTool/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    return normalize_cbdb_payload(payload)


def normalize_cbdb_payload(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        raw_records = payload
    elif isinstance(payload, dict):
        raw_records = (
            payload.get("Package", {}).get("PersonAuthority", {}).get("PersonInfo")
            or payload.get("PersonInfo")
            or payload.get("persons")
            or payload.get("data")
            or payload.get("items")
            or []
        )
        if isinstance(raw_records, dict):
            raw_records = [raw_records]
    else:
        raw_records = []
    records = []
    for item in raw_records:
        if isinstance(item, dict):
            records.append(item)
    return records


def import_cbdb_records(records: list[dict[str, Any]], fallback_name: str = "") -> dict[str, Any]:
    imported = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    with db() as conn:
        existing = {
            (row["type"], row["normalized_text"], row["canonical_id"])
            for row in conn.execute("SELECT type, normalized_text, canonical_id FROM knowledge_terms").fetchall()
        }
        now = utc_now()
        for record in records:
            person = _record_to_term(record, fallback_name)
            if not person["text"]:
                errors.append({"name": fallback_name, "error": "CBDB record has no usable name."})
                continue
            key = ("person_name", person["normalized_text"], person["canonical_id"])
            if key in existing:
                skipped += 1
                continue
            conn.execute(
                """
                INSERT INTO knowledge_terms
                (type, canonical_id, text, normalized_text, aliases_json, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "person_name",
                    person["canonical_id"],
                    person["text"],
                    person["normalized_text"],
                    json_dumps(person["aliases"]),
                    json_dumps(person["metadata"]),
                    now,
                ),
            )
            existing.add(key)
            imported += 1
    return {"imported": imported, "skipped": skipped, "errors": errors}


def _collect_names(names: list[str], include_extracted: bool, include_terms: bool) -> list[str]:
    values = {name.strip() for name in names if name and name.strip()}
    if include_extracted or include_terms:
        with db() as conn:
            if include_extracted:
                values.update(
                    row["text"]
                    for row in conn.execute("SELECT DISTINCT text FROM entities WHERE entity_type='PER'").fetchall()
                    if row["text"]
                )
            if include_terms:
                values.update(
                    row["text"]
                    for row in conn.execute("SELECT DISTINCT text FROM knowledge_terms WHERE type='person_name'").fetchall()
                    if row["text"]
                )
    return sorted(values)


def _record_to_term(record: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    cbdb_id = _first_value(record, ("c_personid", "personid", "id", "PersonId", "PersonID"))
    name = _first_value(record, ("c_name_chn", "name", "Name", "姓名", "person_name")) or fallback_name
    aliases = _aliases(record, name)
    metadata = {
        "source": "CBDB",
        "raw": record,
        "updated_at": utc_now(),
    }
    canonical_id = f"CBDB-{cbdb_id}" if cbdb_id else f"CBDB-NAME-{compact_text(name)}"
    return {
        "canonical_id": canonical_id,
        "text": name,
        "normalized_text": to_traditional(compact_text(name)),
        "aliases": aliases,
        "metadata": metadata,
    }


def _first_value(record: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _aliases(record: dict[str, Any], name: str) -> list[str]:
    aliases: set[str] = set()
    for key in ("aliases", "alias", "alt_names", "c_alt_name", "c_name", "字", "號"):
        value = record.get(key)
        if isinstance(value, list):
            aliases.update(str(item).strip() for item in value if str(item).strip())
        elif value:
            aliases.update(item.strip() for item in str(value).replace(";", ",").split(",") if item.strip())
    aliases.discard(name)
    return sorted(aliases)
