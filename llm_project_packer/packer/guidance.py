"""Per-destination packaging guidance.

Each packaging destination rewards a different set of levers. These short
cheat-sheets — distilled from the chunking/packaging research in the repo root
(``Claude Research Chunking and Slicing A/B.md``, ``deep-research-report-
Chatgpt.md``) — are surfaced in the generated instruction files and the UI so
the user does not have to guess which toggles actually move the needle for the
product they are building.

Verdict vocabulary: **Effective** (worth doing), **Inert** (no measurable
effect — don't bother), **Harmful** (backfires).
"""

from __future__ import annotations

from typing import Dict, List

# Canonical destination keys (also used as ``Profile.destination`` values).
DEST_SELF_HOSTED_RAG = "self_hosted_rag"
DEST_CLAUDE_PROJECT = "claude_project"
DEST_CHATGPT_PROJECT = "chatgpt_project"
DEST_CHATGPT_ENTERPRISE = "chatgpt_enterprise"

DESTINATIONS = (
    DEST_SELF_HOSTED_RAG,
    DEST_CLAUDE_PROJECT,
    DEST_CHATGPT_PROJECT,
    DEST_CHATGPT_ENTERPRISE,
)

DESTINATION_LABELS: Dict[str, str] = {
    DEST_SELF_HOSTED_RAG: "Self-hosted / custom RAG (you own the embedder + store)",
    DEST_CLAUDE_PROJECT: "Claude Project",
    DEST_CHATGPT_PROJECT: "ChatGPT Project / custom GPT",
    DEST_CHATGPT_ENTERPRISE: "ChatGPT Enterprise / government workspace (\"DHS chat\")",
}

_GUIDANCE: Dict[str, List[str]] = {
    DEST_SELF_HOSTED_RAG: [
        "Your chunk *is* the retrieval unit, so chunking is a first-class lever here "
        "(unlike the hosted destinations).",
        "**Effective:** structure-aware chunks (split at headings, keep code/tables "
        "intact), ~256–512 tokens for BGE/E5-class embedders (512-token cap) or up to "
        "1–2K for Nomic/Arctic-class (8192 cap); merge tiny fragments.",
        "**Effective:** heading-breadcrumb context on each chunk (metadata and/or "
        "prefixed into the text) — the cheapest structural lever, biggest help on long "
        "documents; A/B test it on your corpus rather than assuming a fixed lift.",
        "**Effective:** stable doc IDs + rich per-chunk metadata (appellant, PA ID, "
        "disaster, date, region, status, cited authorities) for citation and metadata "
        "filtering; hybrid keyword + vector search with a reranker beats vectors alone.",
        "**Neutral:** chunk overlap — recent evidence shows little benefit for "
        "structure-aware chunks; reserve a small overlap for boundary-sensitive text.",
    ],
    DEST_CLAUDE_PROJECT: [
        "Claude loads full project text into context until it crosses its threshold, "
        "then switches to its own RAG over its own index — your chunk boundaries are "
        "discarded either way.",
        "**Effective:** bundle into a few complete, well-structured Markdown files; "
        "keep total knowledge under the in-context threshold (~200K standard / 500K on "
        "some plans) to stay out of RAG mode.",
        "**Effective:** hard content selection (strip boilerplate), clean headings, "
        "descriptive filenames, and stable DOC_IDs for reference-by-name.",
        "**Harmful:** pre-splitting into many small files — more files push Claude into "
        "RAG mode sooner and fragment context. Do NOT upload your `chunks.jsonl`.",
    ],
    DEST_CHATGPT_PROJECT: [
        "ChatGPT re-parses, re-chunks (~800-token / 400-overlap on its side), and "
        "hybrid-searches your files — your external chunk tuning is discarded.",
        "**Effective:** a few complete, text-forward Markdown files or modest topical "
        "bundles; respect the file-slot caps (custom GPTs: up to 20 files).",
        "**Effective:** clean headings, boilerplate removal, a README/index file, and "
        "stable filenames/DOC_IDs for citation and retrieval targeting.",
        "**Inert/Harmful:** external chunk size, overlap, and micro-chunk uploads — they "
        "waste file slots and are re-chunked anyway.",
    ],
    DEST_CHATGPT_ENTERPRISE: [
        "Documented pipeline: ChatGPT stuffs ~110K tokens into context and pushes the "
        "rest into a private hybrid (keyword + semantic) search index. Content past the "
        "stuffing budget in an oversize file is retrieval-only.",
        "**Effective:** medium-grained, focused files — NOT one mega-bundle (content "
        "gets stranded past ~110K) and NOT thousands of micro-chunks (they fragment the "
        "per-file stuffing budget). Split very large sources at major headings.",
        "**Effective:** put overview/index material early in each file; fewer focused "
        "documents generally raise accuracy; keep stable DOC_IDs + manifest.",
        "**Inert/Harmful:** external chunk-size/overlap tuning and breadcrumb prefixes "
        "duplicated into the body. Treat FedRAMP/Gov deployments like Enterprise unless "
        "an agency deployment guide says otherwise.",
    ],
}


def guidance_for_destination(destination: str) -> List[str]:
    """Return the guidance cheat-sheet lines for ``destination`` (empty if none)."""
    if not destination:
        return []
    return list(_GUIDANCE.get(destination, []))
