"""Bundle converted documents into Markdown files within a token budget."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from . import markdown_utils as mdu
from .manifest import ManifestEntry
from .token_estimator import estimate_tokens, estimator_backend


@dataclass
class ConvertedDoc:
    """A single document, ready to be placed into a bundle."""

    entry: ManifestEntry
    body_markdown: str  # the converted body, WITHOUT the identity header
    header_markdown: str  # YAML-style identity header
    token_estimate: int

    @property
    def total_markdown(self) -> str:
        return self.header_markdown + "\n" + self.body_markdown.rstrip() + "\n"


@dataclass
class Bundle:
    """A group of documents that will be written to one Markdown file."""

    index: int  # 1-based
    docs: List[ConvertedDoc] = field(default_factory=list)

    @property
    def filename(self) -> str:
        # Bundles get sequential numeric prefixes starting at 02_ (the manifest is 01_).
        return f"{(self.index + 1):02d}_BUNDLE_{self.index:03d}.md"

    @property
    def name(self) -> str:
        return f"BUNDLE_{self.index:03d}"

    @property
    def total_tokens(self) -> int:
        return sum(d.token_estimate for d in self.docs)

    @property
    def doc_ids(self) -> List[str]:
        return [d.entry.doc_id for d in self.docs]


def split_into_bundles(
    docs: List[ConvertedDoc],
    max_bundle_tokens: int,
) -> List[Bundle]:
    """Greedy bin-packer.

    Adds documents to the current bundle until adding the next one would
    overflow the token budget; then starts a new bundle. Documents larger
    than the budget on their own are placed in a bundle by themselves.
    """
    bundles: List[Bundle] = []
    current = Bundle(index=1)
    current_tokens = 0

    for doc in docs:
        if not current.docs:
            current.docs.append(doc)
            current_tokens = doc.token_estimate
            continue
        if current_tokens + doc.token_estimate <= max_bundle_tokens:
            current.docs.append(doc)
            current_tokens += doc.token_estimate
        else:
            bundles.append(current)
            current = Bundle(index=len(bundles) + 1)
            current.docs.append(doc)
            current_tokens = doc.token_estimate

    if current.docs:
        bundles.append(current)

    return bundles


def write_bundle(
    bundle: Bundle,
    output_dir: Path,
    *,
    project_name: str,
    target: str,
    mode: str,
    max_bundle_tokens: int,
    total_bundles: int,
) -> Path:
    """Write a bundle file to ``output_dir`` and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    header_lines: List[str] = []
    header_lines.append(f"# {bundle.name} — {project_name}")
    header_lines.append("")
    header_lines.append(f"- **Project:** {project_name}")
    header_lines.append(f"- **Target:** {target}")
    header_lines.append(f"- **Mode:** {mode}")
    header_lines.append(f"- **Bundle:** {bundle.index} of {total_bundles}")
    header_lines.append(f"- **Estimated tokens:** {bundle.total_tokens:,}")
    header_lines.append(f"- **Token budget:** {max_bundle_tokens:,}")
    header_lines.append(f"- **Token estimator backend:** {estimator_backend()}")
    header_lines.append(f"- **Documents in bundle:** {len(bundle.docs)}")
    header_lines.append(
        "- **Included DOC_IDs:** " + ", ".join(bundle.doc_ids)
    )
    header_lines.append("")
    header_lines.append("## How to cite from this bundle")
    header_lines.append("")
    header_lines.append(
        "When you answer questions using these documents, cite both the "
        "`DOC_ID` and the `SOURCE_FILE` shown in each document's identity "
        "header. Prefer exact quotes for technical specifications, "
        "measurements, dates, deadlines, and warnings."
    )
    header_lines.append("")
    header_lines.append(
        "These documents were converted from their original formats. "
        "If a passage looks malformed, refer back to the original file "
        "listed in `SOURCE_PATH`."
    )
    header_lines.append("")

    parts: List[str] = ["\n".join(header_lines)]
    for doc in bundle.docs:
        parts.append(mdu.section_divider())
        parts.append(doc.total_markdown)

    bundle_path = output_dir / bundle.filename
    bundle_path.write_text("".join(parts), encoding="utf-8")
    return bundle_path


def make_converted_doc(entry: ManifestEntry, body_markdown: str) -> ConvertedDoc:
    """Build a ConvertedDoc and compute its token estimate including the header."""
    header = mdu.doc_header(
        doc_id=entry.doc_id,
        source_file=entry.source_file,
        source_path=entry.source_path,
        original_extension=entry.original_extension,
    )
    full = header + "\n" + (body_markdown or "")
    tokens = estimate_tokens(full)
    return ConvertedDoc(
        entry=entry,
        body_markdown=body_markdown or "",
        header_markdown=header,
        token_estimate=tokens,
    )
