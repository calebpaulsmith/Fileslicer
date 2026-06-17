"""Bundle converted documents into Markdown files within a token budget."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from . import markdown_utils as mdu
from .chunking import DEFAULT_HEADING_LEVEL, chunk_markdown_by_headings_with_reasons
from .manifest import ManifestEntry
from .token_estimator import estimate_tokens, estimator_backend


@dataclass
class ConvertedDoc:
    """A single document, ready to be placed into a bundle."""

    entry: ManifestEntry
    body_markdown: str  # the converted body, WITHOUT the identity header
    header_markdown: str  # YAML-style identity header
    token_estimate: int
    metadata: Dict[str, Any] = field(default_factory=dict)  # source-specific record metadata

    @property
    def total_markdown(self) -> str:
        return self.header_markdown + "\n" + self.body_markdown.rstrip() + "\n"


@dataclass
class Bundle:
    """A group of documents that will be written to one Markdown file."""

    index: int  # 1-based
    docs: List[ConvertedDoc] = field(default_factory=list)
    prefix_width: int = 2

    @property
    def filename(self) -> str:
        # Bundles get sequential numeric prefixes starting at 02_ (the manifest is
        # 01_). When an export needs wider prefixes, numbering starts at "02"
        # zero-extended (020, 021, ...) so every bundle still sorts after the
        # 00_* instructions and 01_* manifest; plain zero-padding (002) would not.
        prefix = 2 * 10 ** (self.prefix_width - 2) + self.index - 1
        return f"{prefix:0{self.prefix_width}d}_BUNDLE_{self.index:03d}.md"

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

    assign_bundle_prefix_width(bundles)
    return bundles


def assign_bundle_prefix_width(bundles: List[Bundle]) -> List[Bundle]:
    """Set a shared, width-uniform numeric prefix on every bundle (in place).

    The width is chosen so the highest bundle number still fits, keeping every
    bundle sorting after the ``00_*`` instructions and ``01_*`` manifest.
    """
    prefix_width = 2
    while 2 * 10 ** (prefix_width - 2) + len(bundles) - 1 > 10**prefix_width - 1:
        prefix_width += 1
    for bundle in bundles:
        bundle.prefix_width = prefix_width
    return bundles


def _join_notes(existing: str, addition: str) -> str:
    existing = (existing or "").strip()
    return f"{existing} {addition}".strip() if existing else addition


def split_doc_at_headings(
    doc: ConvertedDoc,
    target_tokens: int,
    heading_level: int = DEFAULT_HEADING_LEVEL,
) -> List[ConvertedDoc]:
    """Split one oversize document into part documents at its major headings.

    Used by the medium-grained bundling mode so a single document larger than
    the per-bundle budget is broken into focused, in-budget files at major
    heading boundaries instead of becoming one stranded oversize bundle. A
    document already within ``target_tokens``, or one with no headings to split
    on, is returned unchanged as a single-element list. Parts get derived
    ``DOC_xxxx_pNN`` ids and explanatory manifest notes.
    """
    if target_tokens <= 0 or doc.token_estimate <= target_tokens:
        return [doc]
    body = doc.body_markdown.strip()
    pairs = chunk_markdown_by_headings_with_reasons(body, target_tokens, heading_level)
    if len(pairs) <= 1:
        return [doc]
    total = len(pairs)
    parts: List[ConvertedDoc] = []
    for i, (text, _reason) in enumerate(pairs, start=1):
        entry = replace(
            doc.entry,
            doc_id=f"{doc.entry.doc_id}_p{i:02d}",
            notes=_join_notes(doc.entry.notes, f"Part {i} of {total} (medium heading split)"),
        )
        part = make_converted_doc(entry, text)
        entry.token_estimate = part.token_estimate
        entry.char_count = len(text)
        entry.word_count = len(text.split())
        parts.append(part)
    return parts


def split_into_bundles_medium(
    docs: List[ConvertedDoc],
    target_tokens: int,
    heading_level: int = DEFAULT_HEADING_LEVEL,
) -> List[Bundle]:
    """Medium-grained bundling: split oversize docs at headings, then bin-pack.

    Each document larger than ``target_tokens`` is first broken into in-budget
    part documents at major headings (see :func:`split_doc_at_headings`); the
    resulting documents are then packed with the same greedy packer and
    byte-identical numbering as :func:`split_into_bundles`. The intent (for the
    ChatGPT Enterprise / "DHS chat" destination) is medium-grained focused
    files: no single bundle exceeds the stuffing budget and no content is
    stranded deep inside an oversize file.
    """
    prepared: List[ConvertedDoc] = []
    for doc in docs:
        prepared.extend(split_doc_at_headings(doc, target_tokens, heading_level))
    return split_into_bundles(prepared, target_tokens)


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


def make_converted_doc(
    entry: ManifestEntry,
    body_markdown: str,
    metadata: Optional[Mapping[str, Any]] = None,
) -> ConvertedDoc:
    """Build a ConvertedDoc and compute its token estimate including the header.

    ``metadata`` is optional source-specific record metadata (e.g. an appeal's
    appellant, disaster, and cited authorities) that downstream RAG exports
    attach to each chunk; it defaults to empty so folder-sourced documents are
    unaffected.
    """
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
        metadata=dict(metadata) if metadata else {},
    )
