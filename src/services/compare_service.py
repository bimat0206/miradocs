"""Deterministic document comparison service."""
import json
import re
import uuid
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.intake.document_registry import DocumentRegistry

COMPARE_MODES = {
    "auto",
    "hld_lld",
    "requirements_design",
    "requirements_test",
    "policy_architecture",
    "sow_design",
    "version_diff",
    "generic_diff",
}

TOPICS_BY_MODE = {
    "hld_lld": ["network", "security", "logging", "backup", "monitoring", "encryption", "disaster recovery"],
    "requirements_design": ["availability", "security", "logging", "monitoring", "backup", "performance"],
    "requirements_test": ["test", "acceptance", "pass", "fail", "coverage"],
    "policy_architecture": ["encryption", "mfa", "logging", "iam", "retention", "audit"],
    "sow_design": ["deliverable", "scope", "milestone", "backup", "security", "network"],
    "generic_diff": ["security", "network", "logging", "backup", "monitoring"],
}


class CompareError(ValueError):
    pass


def detect_compare_mode(source_doc: dict, target_doc: dict, data_dir: Path | None = None) -> dict:
    source_text = _doc_hint_text(source_doc)
    target_text = _doc_hint_text(target_doc)
    pair = f"{source_text} {target_text}"

    if _has(source_text, "hld") and _has(target_text, "lld") or _has(source_text, "lld") and _has(target_text, "hld"):
        return {"detected_mode": "hld_lld", "confidence": 0.95, "reasons": ["HLD/LLD markers found"]}
    if _has(pair, "requirement") and _has(pair, "test"):
        return {"detected_mode": "requirements_test", "confidence": 0.85, "reasons": ["Requirement and test markers found"]}
    if _has(pair, "requirement") and _has_any(pair, ["design", "architecture", "hld", "lld"]):
        return {"detected_mode": "requirements_design", "confidence": 0.82, "reasons": ["Requirement and design markers found"]}
    if _has_any(pair, ["policy", "standard"]) and _has_any(pair, ["architecture", "design", "hld", "lld"]):
        return {"detected_mode": "policy_architecture", "confidence": 0.8, "reasons": ["Policy and architecture markers found"]}
    if _has_any(pair, ["sow", "statement of work", "contract"]) and _has_any(pair, ["design", "architecture", "hld", "lld"]):
        return {"detected_mode": "sow_design", "confidence": 0.8, "reasons": ["SOW and design markers found"]}
    if _has_any(pair, ["v1", "v2", "version", "revision", "rev"]):
        return {"detected_mode": "version_diff", "confidence": 0.65, "reasons": ["Version markers found"]}
    return {"detected_mode": "generic_diff", "confidence": 0.45, "reasons": ["No specific pair markers found"]}


def run_compare(
    *,
    source_doc_id: str,
    target_doc_id: str,
    mode: str,
    registry: DocumentRegistry,
    data_dir: Path,
) -> dict:
    if source_doc_id == target_doc_id:
        raise CompareError("Compare requires two different documents")
    if mode not in COMPARE_MODES:
        raise CompareError(f"Unsupported compare mode: {mode}")

    source_doc = registry.get_document(source_doc_id)
    target_doc = registry.get_document(target_doc_id)
    if not source_doc or not target_doc:
        raise CompareError("Both documents must exist")

    detected = detect_compare_mode(source_doc, target_doc, data_dir)
    detected_mode = detected["detected_mode"] if mode == "auto" else mode
    source = _load_compare_doc(source_doc, data_dir)
    target = _load_compare_doc(target_doc, data_dir)

    run_id = registry.create_compare_run(
        source_doc_id=source_doc_id,
        target_doc_id=target_doc_id,
        requested_mode=mode,
        detected_mode=detected_mode,
    )
    findings = _dedupe_findings([
        *_section_findings(source, target),
        *_entity_findings(source, target),
        *_value_findings(source, target),
        *_table_findings(source, target),
        *_topic_findings(source, target, detected_mode),
    ])
    summary = _summarize(findings)
    registry.add_compare_findings(run_id, findings)
    registry.complete_compare_run(run_id, status="done", summary=summary)
    result = registry.get_compare_run(run_id)
    if not result:
        raise CompareError("Compare run could not be loaded")
    return result


def _doc_hint_text(doc: dict) -> str:
    values = [
        doc.get("filename", ""),
        doc.get("document_type", ""),
        doc.get("domain", ""),
        " ".join(doc.get("tags", [])),
    ]
    return " ".join(values).lower()


def _load_compare_doc(doc: dict, data_dir: Path) -> dict:
    doc_id = doc["doc_id"]
    parsed_dir = data_dir / "parsed" / doc_id
    structure = _load_json(parsed_dir / "document_structure.json")
    chunks = _load_json(parsed_dir / "chunks.json")
    if structure is None or chunks is None:
        raise CompareError(f"Document {doc_id} must be processed before compare")
    entities_data = _load_json(parsed_dir / "entities.json") or {}
    tables_index = _load_json(data_dir / "tables" / doc_id / "tables_index.json") or []
    tables = []
    for table in tables_index:
        name = table.get("file_md") or table.get("file_csv")
        content = ""
        if name:
            path = data_dir / "tables" / doc_id / Path(name).name
            if path.exists():
                content = path.read_text(encoding="utf-8")
        tables.append({**table, "content": content})
    return {
        "doc": doc,
        "chunks": chunks,
        "sections": _normalize_sections(structure.get("sections", []), chunks),
        "entities": _normalize_entities(entities_data, chunks),
        "tables": tables,
        "text": "\n".join(str(chunk.get("text", "")) for chunk in chunks),
    }


def _section_findings(source: dict, target: dict) -> list[dict]:
    findings = []
    target_titles = [section["norm_title"] for section in target["sections"]]
    source_titles = [section["norm_title"] for section in source["sections"]]
    for section in source["sections"]:
        if _best_similarity(section["norm_title"], target_titles) < 0.72:
            findings.append(_finding(
                "missing_section",
                "high",
                f"Missing section in target: {section['title']}",
                f"Source has section '{section['title']}', but no similar target section was found.",
                source["doc"]["doc_id"],
                target["doc"]["doc_id"],
                source_evidence=[_section_evidence(source["doc"]["doc_id"], section)],
                normalized_key=f"missing_section:{section['norm_title']}",
            ))
    for section in target["sections"]:
        if _best_similarity(section["norm_title"], source_titles) < 0.72:
            findings.append(_finding(
                "extra_section",
                "low",
                f"Extra section in target: {section['title']}",
                f"Target has section '{section['title']}', but no similar source section was found.",
                source["doc"]["doc_id"],
                target["doc"]["doc_id"],
                target_evidence=[_section_evidence(target["doc"]["doc_id"], section)],
                normalized_key=f"extra_section:{section['norm_title']}",
            ))
    return findings


def _entity_findings(source: dict, target: dict) -> list[dict]:
    findings = []
    for entity_type, source_values in source["entities"].items():
        target_values = target["entities"].get(entity_type, {})
        for norm_value, item in source_values.items():
            if norm_value not in target_values:
                findings.append(_finding(
                    "missing_entity",
                    "medium",
                    f"Missing {entity_type}: {item['value']}",
                    f"Source mentions '{item['value']}' but target does not.",
                    source["doc"]["doc_id"],
                    target["doc"]["doc_id"],
                    source_evidence=[_entity_evidence(source["doc"]["doc_id"], item)],
                    normalized_key=f"missing_entity:{entity_type}:{norm_value}",
                ))
    return findings[:50]


def _value_findings(source: dict, target: dict) -> list[dict]:
    specs = [
        ("cidr", r"\b\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}\b", "high"),
        ("account", r"\b\d{12}\b", "high"),
        ("region", r"\b[a-z]{2}-[a-z]+-\d\b", "medium"),
        ("version", r"\bv(?:ersion)?\s*[0-9]+(?:\.[0-9]+)*\b", "low"),
    ]
    findings = []
    for label, pattern, severity in specs:
        source_values = sorted(set(re.findall(pattern, source["text"], flags=re.IGNORECASE)))
        target_values = sorted(set(re.findall(pattern, target["text"], flags=re.IGNORECASE)))
        if source_values and target_values and source_values != target_values:
            findings.append(_finding(
                "value_mismatch",
                severity,
                f"{label.upper()} values differ",
                f"Source values: {', '.join(source_values)}. Target values: {', '.join(target_values)}.",
                source["doc"]["doc_id"],
                target["doc"]["doc_id"],
                source_evidence=[_chunk_evidence(source["doc"]["doc_id"], _first_chunk_with(source["chunks"], source_values[0]))],
                target_evidence=[_chunk_evidence(target["doc"]["doc_id"], _first_chunk_with(target["chunks"], target_values[0]))],
                normalized_key=f"value_mismatch:{label}",
            ))
    return findings


def _table_findings(source: dict, target: dict) -> list[dict]:
    findings = []
    target_tables = {table.get("table_id"): table for table in target["tables"]}
    for table in source["tables"]:
        table_id = table.get("table_id")
        target_table = target_tables.get(table_id)
        if not target_table or not table.get("content") or not target_table.get("content"):
            continue
        if _normalize_table(table["content"]) != _normalize_table(target_table["content"]):
            findings.append(_finding(
                "table_mismatch",
                "medium",
                f"Table differs: {table_id}",
                "A table with the same id exists in both documents, but its content differs.",
                source["doc"]["doc_id"],
                target["doc"]["doc_id"],
                source_evidence=[_table_evidence(source["doc"]["doc_id"], table)],
                target_evidence=[_table_evidence(target["doc"]["doc_id"], target_table)],
                normalized_key=f"table_mismatch:{table_id}",
            ))
    return findings


def _topic_findings(source: dict, target: dict, mode: str) -> list[dict]:
    findings = []
    target_text = target["text"].lower()
    for topic in TOPICS_BY_MODE.get(mode, TOPICS_BY_MODE["generic_diff"]):
        if topic in source["text"].lower() and topic not in target_text:
            findings.append(_finding(
                "topic_gap",
                "low",
                f"Topic missing in target: {topic}",
                f"Source discusses '{topic}', but target text does not contain that topic.",
                source["doc"]["doc_id"],
                target["doc"]["doc_id"],
                source_evidence=[_chunk_evidence(source["doc"]["doc_id"], _first_chunk_with(source["chunks"], topic))],
                normalized_key=f"topic_gap:{topic}",
            ))
    return findings


def _finding(type_: str, severity: str, title: str, description: str, source_doc_id: str, target_doc_id: str, *, source_evidence=None, target_evidence=None, normalized_key: str) -> dict:
    return {
        "finding_id": uuid.uuid4().hex,
        "type": type_,
        "severity": severity,
        "title": title,
        "description": description,
        "source_doc_id": source_doc_id,
        "target_doc_id": target_doc_id,
        "source_evidence": [item for item in (source_evidence or []) if item],
        "target_evidence": [item for item in (target_evidence or []) if item],
        "normalized_key": normalized_key,
        "llm_status": "not_requested",
        "llm_summary": None,
        "llm_recommendation": None,
    }


def _normalize_sections(sections: list[dict], chunks: list[dict]) -> list[dict]:
    result = []
    for section in sections:
        title = section.get("title") or section.get("section_path") or section.get("section_id") or ""
        if not title:
            continue
        chunk = _first_section_chunk(chunks, str(title))
        page_start = _page_value(section, "page_start", "page", "page_number")
        page_end = _page_value(section, "page_end") or page_start
        if not page_start and chunk:
            page_start = _page_value(chunk, "page_start", "page", "page_number")
            page_end = _page_value(chunk, "page_end") or page_start
        result.append({
            "title": str(title),
            "norm_title": _norm(title),
            "page_start": page_start or 1,
            "page_end": page_end or page_start or 1,
            "evidence_text": str(chunk.get("text", ""))[:700] if chunk else str(title),
        })
    return result


def _normalize_entities(data: dict, chunks: list[dict]) -> dict[str, dict[str, dict]]:
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    occurrence_items = data.get("entities", []) if isinstance(data, dict) else []
    summary_items = data.get("summary", []) if isinstance(data, dict) else []
    items = [*(occurrence_items or []), *(summary_items or [])]
    for item in items or []:
        value = item.get("value") or item.get("name") or item.get("text")
        if not value:
            continue
        entity_type = _norm(item.get("type") or item.get("entity_type") or "entity").replace(" ", "_")
        norm_value = _norm(value)
        chunk = _first_chunk_with(chunks, str(value))
        page = _page_value(item, "page", "page_number", "page_start")
        if not page and chunk:
            page = _page_value(chunk, "page_start", "page", "page_number")
        existing = grouped[entity_type].get(norm_value)
        if existing and existing.get("page") and not item.get("page"):
            continue
        grouped[entity_type][norm_value] = {
            "type": entity_type,
            "value": str(value),
            "page": page or 1,
            "section_path": str(chunk.get("section_path", "")) if chunk else "",
            "text": str(chunk.get("text", value))[:700] if chunk else str(value),
        }
    return grouped


def _dedupe_findings(findings: list[dict]) -> list[dict]:
    by_key = {}
    for finding in findings:
        by_key.setdefault(finding["normalized_key"], finding)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(by_key.values(), key=lambda item: (severity_order.get(item["severity"], 9), item["type"], item["title"]))


def _summarize(findings: list[dict]) -> dict:
    return {
        "total": len(findings),
        "by_severity": dict(Counter(finding["severity"] for finding in findings)),
        "by_type": dict(Counter(finding["type"] for finding in findings)),
    }


def _section_evidence(doc_id: str, section: dict) -> dict:
    return {
        "doc_id": doc_id,
        "page": section.get("page_start", 1),
        "section_path": section.get("title", ""),
        "text": section.get("evidence_text") or section.get("title", ""),
    }


def _entity_evidence(doc_id: str, item: dict) -> dict:
    return {
        "doc_id": doc_id,
        "page": item.get("page", 1),
        "section_path": item.get("section_path", ""),
        "text": item.get("text") or item.get("value", ""),
    }


def _chunk_evidence(doc_id: str, chunk: dict | None) -> dict | None:
    if not chunk:
        return None
    return {
        "doc_id": doc_id,
        "page": chunk.get("page_start", 1),
        "section_path": chunk.get("section_path", ""),
        "text": str(chunk.get("text", ""))[:700],
    }


def _table_evidence(doc_id: str, table: dict) -> dict:
    return {
        "doc_id": doc_id,
        "page": table.get("page", 1),
        "section_path": "",
        "text": str(table.get("content", ""))[:700],
        "table_id": table.get("table_id"),
    }


def _first_chunk_with(chunks: list[dict], value: str) -> dict | None:
    needle = str(value).lower()
    return next((chunk for chunk in chunks if needle in str(chunk.get("text", "")).lower()), None)


def _first_section_chunk(chunks: list[dict], title: str) -> dict | None:
    norm_title = _norm(title)
    return next(
        (
            chunk for chunk in chunks
            if norm_title and (
                norm_title in _norm(chunk.get("section_path", ""))
                or norm_title in _norm(chunk.get("text", ""))
            )
        ),
        None,
    )


def _page_value(item: dict, *keys: str) -> int | None:
    for key in keys:
        raw = item.get(key)
        if raw is None:
            continue
        try:
            page = int(raw)
        except (TypeError, ValueError):
            continue
        if page > 0:
            return page
    return None


def _best_similarity(value: str, candidates: list[str]) -> float:
    if not candidates:
        return 0
    return max(SequenceMatcher(None, value, candidate).ratio() for candidate in candidates)


def _normalize_table(content: str) -> str:
    return "\n".join(line.strip().lower() for line in content.splitlines() if line.strip())


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value).lower())).strip()


def _has(text: str, needle: str) -> bool:
    return needle in text.lower()


def _has_any(text: str, needles: list[str]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def _load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
