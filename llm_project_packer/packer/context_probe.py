"""Generate a context-probe export to empirically measure a destination's
effective retrieval window (e.g. whether ChatGPT Enterprise's "~110K stuffing"
behavior holds for *your* workspace).

FileSlicer is local and cannot query a hosted platform, so this tool produces
the *artifacts* for a manual needle-in-a-haystack probe: a set of bundles, each
carrying a unique canary fact, plus a depth file with canaries at increasing
token-depths, plus an answer key and a question list. You upload the bundles to
a fresh project/workspace and ask each canary question; the pattern of correct
vs. wrong answers reveals what the platform actually retrieves and at what depth
it falls off.

Nothing here is hosted or uploaded — it only writes local Markdown files.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from .markdown_utils import safe_filename
from .token_estimator import estimate_tokens

# Deterministic canary codes (no randomness, so the probe is reproducible).
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_FILLER_SENTENCE = (
    "The recipient documented the project scope and the applicant submitted "
    "supporting records for review under the program guidance in effect. "
)


def _canary_code(index: int) -> str:
    """A short, stable, easy-to-read canary code like ``PROBE-A7K2``."""
    value = (index * 2654435761) & 0xFFFFFFFF
    chars = []
    for _ in range(4):
        chars.append(_ALPHABET[value % len(_ALPHABET)])
        value //= len(_ALPHABET)
    return "PROBE-" + "".join(chars)


def _filler(target_tokens: int) -> str:
    """Deterministic neutral filler text of roughly ``target_tokens`` tokens."""
    if target_tokens <= 0:
        return ""
    # ~ estimate per sentence, then pad to the target.
    per = max(1, estimate_tokens(_FILLER_SENTENCE))
    count = max(1, target_tokens // per)
    return (_FILLER_SENTENCE * count).strip()


def _canary_line(code: str, location: str) -> str:
    return (
        f"CANARY {code}: the secret pass phrase for {location} is "
        f"\"{code}-CONFIRMED\". Remember this exact phrase."
    )


@dataclass
class ProbeBundle:
    filename: str
    code: str
    location: str


def build_context_probe(
    output_dir: Path,
    *,
    bundle_tokens: int = 110_000,
    bundles: int = 8,
    project_name: str = "context_probe",
) -> Path:
    """Write a context-probe export under ``output_dir`` and return its folder.

    ``bundle_tokens`` sizes each probe bundle (default 110K, the ChatGPT
    Enterprise stuffing budget). ``bundles`` is the number of cross-file probe
    bundles. A separate depth file places canaries at 10/30/50/70/90/110/150%
    of ``bundle_tokens`` to find the in-file stuffing cutoff.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = output_dir / safe_filename(f"{project_name}_probe_{timestamp}")
    folder.mkdir(parents=True, exist_ok=True)

    made: List[ProbeBundle] = []

    # Cross-file probes: one canary near the middle of each ~bundle_tokens file.
    for i in range(1, bundles + 1):
        code = _canary_code(i)
        location = f"bundle {i}"
        half = _filler(bundle_tokens // 2)
        body = (
            f"# Probe Bundle {i}\n\n{half}\n\n{_canary_line(code, location)}\n\n{half}\n"
        )
        name = f"{i + 1:02d}_PROBE_BUNDLE_{i:03d}.md"
        (folder / name).write_text(body, encoding="utf-8")
        made.append(ProbeBundle(name, code, location))

    # In-file depth probe: canaries at increasing token-depths inside one file.
    depth_pcts = [10, 30, 50, 70, 90, 110, 150]
    depth_parts: List[str] = ["# Probe Depth File\n"]
    depth_made: List[ProbeBundle] = []
    last = 0
    for pct in depth_pcts:
        target_depth = int(bundle_tokens * pct / 100)
        depth_parts.append(_filler(max(0, target_depth - last)))
        last = target_depth
        code = _canary_code(1000 + pct)
        loc = f"depth {pct}%"
        depth_parts.append("\n\n" + _canary_line(code, loc) + "\n\n")
        depth_made.append(ProbeBundle("01_PROBE_DEPTH_FILE.md", code, loc))
    (folder / "01_PROBE_DEPTH_FILE.md").write_text("".join(depth_parts), encoding="utf-8")

    _write_answer_key(folder, project_name, bundle_tokens, made, depth_made)
    _write_instructions(folder, bundle_tokens, bundles)
    return folder


def _write_answer_key(
    folder: Path,
    project_name: str,
    bundle_tokens: int,
    bundles: List[ProbeBundle],
    depth: List[ProbeBundle],
) -> None:
    lines = [
        f"# Context Probe — Answer Key ({project_name})",
        "",
        f"- Bundle size target: {bundle_tokens:,} tokens",
        "- Keep this file to yourself; do NOT upload it to the workspace.",
        "",
        "## Cross-file canaries (upload every `*_PROBE_BUNDLE_*.md`)",
        "",
        "| Question to ask | Correct answer |",
        "| --- | --- |",
    ]
    for b in bundles:
        lines.append(
            f"| What is the secret pass phrase for {b.location}? | `{b.code}-CONFIRMED` |"
        )
    lines += [
        "",
        "## In-file depth canaries (from `01_PROBE_DEPTH_FILE.md`)",
        "",
        "| Question to ask | Correct answer |",
        "| --- | --- |",
    ]
    for b in depth:
        lines.append(
            f"| What is the secret pass phrase for {b.location}? | `{b.code}-CONFIRMED` |"
        )
    lines.append("")
    (folder / "PROBE_ANSWER_KEY.md").write_text("\n".join(lines), encoding="utf-8")


def _write_instructions(folder: Path, bundle_tokens: int, bundles: int) -> None:
    text = f"""# Context Probe — How to run it

This export measures what your destination (e.g. a ChatGPT Enterprise / "DHS
chat" project) actually retrieves, so you can confirm the ~{bundle_tokens:,}-token
working-context assumption for *your* workspace.

## Steps

1. Create a brand-new project / workspace (no other knowledge attached).
2. Upload every `*_PROBE_BUNDLE_*.md` and `01_PROBE_DEPTH_FILE.md`.
   Do **not** upload `PROBE_ANSWER_KEY.md`.
3. Ask each question from `PROBE_ANSWER_KEY.md`, one at a time, in a fresh chat.
   Each answer is a unique `PROBE-XXXX-CONFIRMED` phrase that appears in exactly
   one place, so there is no way to guess it — the model must retrieve it.
4. Record which questions are answered correctly.

## How to read the results

- **Cross-file canaries** ({bundles} of them): if early bundles are answered but
  later ones are not, the platform is only pulling a subset of files into
  context — that is the practical breadth of its retrieval.
- **Depth canaries** (10% → 150% of one file): the depth at which answers start
  failing is the in-file "stuffing" cutoff. If 10–90% succeed but 110%/150% fail,
  the ~{bundle_tokens:,}-token-per-file stuffing budget is confirmed for your
  workspace; content past it is retrieval-only and may be missed.

## Caveat

Results depend on the live platform and can change with model/version updates.
Re-run the probe whenever the workspace's model changes (e.g. a GPT-5.x upgrade).
This tool only generates files; you upload and ask the questions yourself.
"""
    (folder / "00_PROBE_INSTRUCTIONS.md").write_text(text, encoding="utf-8")
