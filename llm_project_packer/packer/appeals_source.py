"""Read FEMA Public Assistance appeal records from a ``pa_rag`` SQLite database.

This is an alternative document source to the recursive folder scanner: instead
of converting files on disk, it queries the canonical ``final_appeal_authority``
table (the manually reviewed, source-of-truth appeal records) and renders one
clean Markdown document per appeal — overview metadata first, then the decision
prose — so the rest of the packaging pipeline (bundle / chunk / export) can be
reused unchanged.

Each appeal becomes a ``ConvertedDoc`` with a stable ``DOC_xxxx`` id and a
manifest entry. Per-appeal failures are isolated: a single bad row is recorded
as ``status="failed"`` and the run continues (repository rule 4).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .bundler import ConvertedDoc, make_converted_doc
from .manifest import Manifest, ManifestEntry
from .markdown_utils import doc_id_for_index, normalize_newlines, safe_filename

# Original-extension label recorded in each appeal's identity header; FEMA
# second-appeal decisions originate as HTML pages.
_APPEAL_EXTENSION = ".html"
_FILE_TYPE = "appeal"

# Maximum number of distinct cited authorities listed in an appeal's overview
# block, ordered by how often they occur in the decision. Keeps the metadata
# line from ballooning on heavily cited appeals.
_MAX_CITATIONS = 40

# (column, heading) pairs rendered as prose sections, overview-first. Empty
# columns are skipped.
_SECTION_FIELDS: Sequence[Tuple[str, str]] = (
    ("final_summary_text", "Summary"),
    ("final_analysis_text", "Analysis"),
    ("final_conclusion_text", "Conclusion"),
    ("final_letter_text", "Decision Letter"),
    ("final_headnotes_text", "Headnotes"),
    ("final_authorities_text", "Authorities"),
    ("final_footnotes_text", "Footnotes"),
)

EmitFn = Callable[[str, str, Optional[Dict[str, Any]]], None]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _load_citations_by_appeal(conn: sqlite3.Connection) -> Dict[str, List[str]]:
    """Map each appeal's ``html_doc_key`` to its distinct cited authorities.

    Citations live in ``document_citation`` keyed by ``parent_doc_key`` (the
    appeal's ``html_doc_key``) and resolve to a human label via
    ``citation_reference``. Returns an empty map if either table is absent.
    """
    if not (_table_exists(conn, "document_citation") and _table_exists(conn, "citation_reference")):
        return {}
    rows = conn.execute(
        """
        SELECT dc.parent_doc_key AS key, cr.canonical_label AS label, COUNT(*) AS n
        FROM document_citation dc
        JOIN citation_reference cr ON cr.citation_id = dc.citation_id
        WHERE cr.canonical_label IS NOT NULL AND TRIM(cr.canonical_label) <> ''
              AND dc.parent_doc_key IS NOT NULL
        GROUP BY dc.parent_doc_key, cr.canonical_label
        ORDER BY dc.parent_doc_key, n DESC, cr.canonical_label
        """
    ).fetchall()
    by_key: Dict[str, List[str]] = {}
    for row in rows:
        by_key.setdefault(row["key"], []).append(row["label"])
    return by_key


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _render_appeal_markdown(
    row: sqlite3.Row,
    citations: List[str],
) -> Tuple[str, str]:
    """Return ``(title, body_markdown)`` for one appeal row."""
    title = _clean(row["final_title"]) or _clean(row["final_appellant"]) or _clean(
        row["final_recipient"]
    ) or f"Appeal {row['final_id']}"

    overview: List[Tuple[str, str]] = [
        ("Appellant", _clean(row["final_appellant"])),
        ("Recipient", _clean(row["final_recipient"])),
        ("PA ID", _clean(row["final_pa_id"])),
        (
            "Disaster",
            " ".join(
                p
                for p in (
                    _clean(row["final_disaster_number_raw"]),
                    f"(norm {_clean(row['final_disaster_number_norm'])})"
                    if _clean(row["final_disaster_number_norm"])
                    else "",
                )
                if p
            ),
        ),
        ("Decision signed", _clean(row["final_decision_signed_date"])),
        ("Declaration date", _clean(row["final_declaration_date"])),
        ("Region", _clean(row["final_region"])),
        ("Status", _clean(row["final_status"])),
        ("PW / GMP", _clean(row["final_pw_gmp_compact"])),
        ("GMP number", _clean(row["final_gmp_number"])),
        ("PW number", _clean(row["final_pw_number"])),
        ("FEMA source key", _clean(row["html_doc_key"])),
    ]

    lines: List[str] = [f"# {title}", "", "## Appeal Overview", ""]
    for label, value in overview:
        if value:
            lines.append(f"- **{label}:** {value}")
    if citations:
        shown = citations[:_MAX_CITATIONS]
        suffix = "" if len(citations) <= _MAX_CITATIONS else f" (+{len(citations) - _MAX_CITATIONS} more)"
        lines.append(f"- **Cited authorities:** {'; '.join(shown)}{suffix}")
    else:
        lines.append("- **Cited authorities:** none extracted")
    lines.append("")

    rendered_section = False
    for column, heading in _SECTION_FIELDS:
        text = _clean(row[column])
        if not text:
            continue
        rendered_section = True
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(text)
        lines.append("")

    if not rendered_section:
        body = _clean(row["final_body_text"])
        if body:
            lines.append("## Decision")
            lines.append("")
            lines.append(body)
            lines.append("")

    return title, normalize_newlines("\n".join(lines))


def _appeal_metadata(row: sqlite3.Row, title: str, citations: List[str]) -> Dict[str, Any]:
    """Structured per-appeal metadata attached to each RAG chunk for filtering/citation."""
    fields = {
        "title": title,
        "appellant": _clean(row["final_appellant"]),
        "recipient": _clean(row["final_recipient"]),
        "pa_id": _clean(row["final_pa_id"]),
        "disaster_number": _clean(row["final_disaster_number_norm"])
        or _clean(row["final_disaster_number_raw"]),
        "decision_date": _clean(row["final_decision_signed_date"]),
        "region": _clean(row["final_region"]),
        "status": _clean(row["final_status"]),
        "final_id": row["final_id"],
        "source_key": _clean(row["html_doc_key"]),
    }
    metadata: Dict[str, Any] = {k: v for k, v in fields.items() if v not in ("", None)}
    if citations:
        metadata["citations"] = list(citations)
    return metadata


def load_appeal_docs(
    db_path: Path,
    manifest: Manifest,
    *,
    warnings: List[str],
    errors: List[str],
    emit: EmitFn,
    limit: Optional[int] = None,
) -> List[ConvertedDoc]:
    """Load finalized appeals from ``db_path`` as ``ConvertedDoc`` objects.

    Appeals are ordered deterministically by ``final_id`` so the assigned
    ``DOC_xxxx`` ids are stable across runs of the same database. Each appeal's
    manifest entry is appended to ``manifest``. A row that fails to render is
    recorded as ``status="failed"`` and skipped; a missing canonical table is a
    fatal configuration error and raises ``ValueError``.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "final_appeal_authority"):
            raise ValueError(
                f"{db_path} does not contain a 'final_appeal_authority' table; "
                "this does not look like a pa_rag appeals database."
            )
        has_html = _table_exists(conn, "src_html_appeal")
        join = (
            "LEFT JOIN src_html_appeal h ON h.html_id = f.html_id"
            if has_html
            else ""
        )
        html_key = "h.html_doc_key AS html_doc_key" if has_html else "NULL AS html_doc_key"
        query = (
            f"SELECT f.final_id, f.html_id, {html_key}, "
            "f.final_title, f.final_appellant, f.final_recipient, f.final_pa_id, "
            "f.final_disaster_number_raw, f.final_disaster_number_norm, "
            "f.final_decision_signed_date, f.final_declaration_date, "
            "f.final_pw_gmp_compact, f.final_gmp_number, f.final_pw_number, "
            "f.final_region, f.final_status, "
            "f.final_summary_text, f.final_analysis_text, f.final_conclusion_text, "
            "f.final_letter_text, f.final_headnotes_text, f.final_authorities_text, "
            "f.final_footnotes_text, f.final_body_text "
            f"FROM final_appeal_authority f {join} ORDER BY f.final_id"
        )
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        citations_by_key = _load_citations_by_appeal(conn)
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()

    converted: List[ConvertedDoc] = []
    for index, row in enumerate(rows, start=1):
        doc_id = doc_id_for_index(index)
        final_id = row["final_id"]
        try:
            citations = citations_by_key.get(_clean(row["html_doc_key"]), [])
            title, body = _render_appeal_markdown(row, citations)
            metadata = _appeal_metadata(row, title, citations)
            source_file = safe_filename(f"appeal_{final_id}_{title}", max_length=100) + ".md"
            entry = ManifestEntry(
                doc_id=doc_id,
                source_file=source_file,
                source_path=f"appeals/{source_file}",
                original_extension=_APPEAL_EXTENSION,
                file_type=_FILE_TYPE,
                status="ok",
                char_count=len(body),
                word_count=len(body.split()),
                notes=f"final_appeal_authority.final_id={final_id}",
            )
            doc = make_converted_doc(entry, body, metadata=metadata)
            entry.token_estimate = doc.token_estimate
            manifest.add(entry)
            converted.append(doc)
            emit(
                "file_start",
                f"  Loaded {doc_id} appeal {final_id} ({entry.token_estimate:,} tokens).",
                {"doc_id": doc_id, "final_id": final_id},
            )
        except Exception as exc:  # noqa: BLE001 - per-appeal isolation (rule 4)
            message = f"Failed to render appeal final_id={final_id}: {exc}"
            errors.append(message)
            emit("warning", f"  Warning: {message}", {"final_id": final_id})
            manifest.add(
                ManifestEntry(
                    doc_id=doc_id,
                    source_file=f"appeal_{final_id}.md",
                    source_path=f"appeals/appeal_{final_id}.md",
                    original_extension=_APPEAL_EXTENSION,
                    file_type=_FILE_TYPE,
                    status="failed",
                    notes=message,
                )
            )
    return converted
