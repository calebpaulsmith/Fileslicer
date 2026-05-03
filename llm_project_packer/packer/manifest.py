"""Source manifest model and writers (Markdown / CSV / JSON)."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from . import markdown_utils as mdu


@dataclass
class ManifestEntry:
    """One row of the source manifest."""

    doc_id: str
    source_file: str
    source_path: str
    original_extension: str
    file_type: str
    status: str  # ok | failed | skipped
    token_estimate: int = 0
    char_count: int = 0
    word_count: int = 0
    notes: str = ""
    output_bundle: str = ""  # filename of bundle this doc landed in (or "" for skipped/failed)


@dataclass
class Manifest:
    """Ordered collection of manifest entries."""

    project_name: str
    target: str
    mode: str
    entries: List[ManifestEntry] = field(default_factory=list)

    def add(self, entry: ManifestEntry) -> None:
        self.entries.append(entry)

    def get(self, doc_id: str) -> Optional[ManifestEntry]:
        for e in self.entries:
            if e.doc_id == doc_id:
                return e
        return None

    # -- writers ---------------------------------------------------------

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "doc_id",
            "source_file",
            "source_path",
            "original_extension",
            "file_type",
            "status",
            "token_estimate",
            "char_count",
            "word_count",
            "notes",
            "output_bundle",
        ]
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for entry in self.entries:
                writer.writerow(asdict(entry))

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": self.project_name,
            "target": self.target,
            "mode": self.mode,
            "entries": [asdict(e) for e in self.entries],
        }
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def write_markdown(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: List[str] = []
        lines.append(f"# Source Manifest — {self.project_name}\n")
        lines.append(f"- **Target:** {self.target}")
        lines.append(f"- **Mode:** {self.mode}")
        lines.append(f"- **Total documents:** {len(self.entries)}")
        ok = sum(1 for e in self.entries if e.status == "ok")
        skipped = sum(1 for e in self.entries if e.status == "skipped")
        failed = sum(1 for e in self.entries if e.status == "failed")
        lines.append(f"- **OK:** {ok}  |  **Skipped:** {skipped}  |  **Failed:** {failed}")
        total_tokens = sum(e.token_estimate for e in self.entries)
        lines.append(f"- **Estimated total tokens:** {total_tokens:,}\n")

        headers = [
            "DOC_ID",
            "Source File",
            "Path",
            "Type",
            "Status",
            "Tokens",
            "Chars",
            "Words",
            "Bundle",
            "Notes",
        ]
        rows = [
            (
                e.doc_id,
                e.source_file,
                e.source_path,
                e.file_type,
                e.status,
                f"{e.token_estimate:,}",
                f"{e.char_count:,}",
                f"{e.word_count:,}",
                e.output_bundle or "-",
                e.notes or "-",
            )
            for e in self.entries
        ]
        lines.append(mdu.rows_to_markdown_table(headers, rows))
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
