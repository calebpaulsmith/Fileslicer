"""Streamlit UI for llm_project_packer.

Run with::

    pip install -r requirements-ui.txt
    streamlit run streamlit_app.py

The UI lets the user load and save profiles, scan a source folder, review
included files, preview the planned bundle shape, and create local export
folders through the shared backend. The CLI (``pack_project.py``) is unchanged.
"""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from collections import Counter, defaultdict
from hashlib import sha1
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent
PACKER_PARENT = REPO_ROOT / "llm_project_packer"
if str(PACKER_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKER_PARENT))

import streamlit as st  # noqa: E402

from packer import presets  # noqa: E402
from packer.chunking import (  # noqa: E402
    DEFAULT_HEADING_LEVEL,
    STRATEGY_HEADINGS,
    STRATEGY_TOKENS,
    match_heading_patterns,
)
from packer.exporters import InstructionContext, write_instructions  # noqa: E402
from packer.markdown_utils import safe_filename  # noqa: E402
from packer.pipeline import (  # noqa: E402
    DocumentChunkPreview,
    PackResult,
    ProgressEvent,
    chunking_guidance,
    preview_document_chunks,
    run_packaging_job,
)
from packer.profiles import (  # noqa: E402
    Profile,
    delete_profile,
    get_built_in_profile,
    list_built_in_profiles,
    list_profiles,
    load_profile,
    save_profile,
)
from packer.scanner import ScannedFile, match_path_patterns, scan_directory  # noqa: E402


PAGE_TITLE = "llm_project_packer"
SESSION_KEY_PROFILE = "current_profile"
SESSION_KEY_LAST_LOADED = "last_loaded_label"
SESSION_KEY_GEN = "form_generation"
SESSION_KEY_SCAN_CACHE = "scan_cache"
SESSION_KEY_FILE_SELECTIONS = "file_review_selections"
SESSION_KEY_FILE_SELECTION_REVISIONS = "file_review_selection_revisions"
SESSION_KEY_CHUNK_SELECTIONS = "chunk_review_selections"
SESSION_KEY_CHUNK_PREVIEWS = "chunk_preview_cache"
SESSION_KEY_CHUNK_REVISIONS = "chunk_review_revisions"
SESSION_KEY_CORPUS_AUDIT = "corpus_chunk_audit"
SESSION_KEY_LAST_EXPORT_RESULT = "last_export_result"
BUNDLE_SEPARATOR_OPTIONS = ("comment", "rule", "blank")
FILE_TYPE_ORDER = (
    "text",
    "html",
    "pdf",
    "docx",
    "csv",
    "xlsx",
    "json",
    "image",
    "unsupported",
)
DEFAULT_CHUNK_REVIEW_TOKENS = 800
CHUNK_STRATEGY_LABELS = {
    STRATEGY_TOKENS: "Token budget (pack paragraphs)",
    STRATEGY_HEADINGS: "Heading sections (split at headings)",
}


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------


def _new_blank_profile() -> Profile:
    return Profile(profile_name="Untitled profile")


def _ensure_session_state() -> None:
    """Initialize session keys exactly once per browser session."""
    if SESSION_KEY_PROFILE not in st.session_state:
        st.session_state[SESSION_KEY_PROFILE] = _new_blank_profile()
    if SESSION_KEY_LAST_LOADED not in st.session_state:
        st.session_state[SESSION_KEY_LAST_LOADED] = "(blank)"
    if SESSION_KEY_GEN not in st.session_state:
        st.session_state[SESSION_KEY_GEN] = 0
    if SESSION_KEY_SCAN_CACHE not in st.session_state:
        st.session_state[SESSION_KEY_SCAN_CACHE] = {}
    if SESSION_KEY_FILE_SELECTIONS not in st.session_state:
        st.session_state[SESSION_KEY_FILE_SELECTIONS] = {}
    if SESSION_KEY_FILE_SELECTION_REVISIONS not in st.session_state:
        st.session_state[SESSION_KEY_FILE_SELECTION_REVISIONS] = {}
    if SESSION_KEY_CHUNK_SELECTIONS not in st.session_state:
        st.session_state[SESSION_KEY_CHUNK_SELECTIONS] = {}
    if SESSION_KEY_CHUNK_PREVIEWS not in st.session_state:
        st.session_state[SESSION_KEY_CHUNK_PREVIEWS] = {}
    if SESSION_KEY_CHUNK_REVISIONS not in st.session_state:
        st.session_state[SESSION_KEY_CHUNK_REVISIONS] = {}
    if SESSION_KEY_CORPUS_AUDIT not in st.session_state:
        st.session_state[SESSION_KEY_CORPUS_AUDIT] = {}
    if SESSION_KEY_LAST_EXPORT_RESULT not in st.session_state:
        st.session_state[SESSION_KEY_LAST_EXPORT_RESULT] = None


def _set_profile(profile: Profile, label: str) -> None:
    """Replace the current profile and bump the form generation counter.

    Bumping the counter changes every widget key, which forces Streamlit to
    re-render with the freshly loaded profile values instead of holding onto
    stale user-typed widget state.
    """
    st.session_state[SESSION_KEY_PROFILE] = profile
    st.session_state[SESSION_KEY_LAST_LOADED] = label
    st.session_state[SESSION_KEY_GEN] += 1


def _profile() -> Profile:
    return st.session_state[SESSION_KEY_PROFILE]


def _gen() -> int:
    return st.session_state[SESSION_KEY_GEN]


def _key(name: str) -> str:
    return f"{name}__g{_gen()}"


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------


def _csv_to_list(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _list_to_csv(values: List[str]) -> str:
    return ", ".join(values)


def _safe_index(options: List[str], value: str, default: int = 0) -> int:
    return options.index(value) if value in options else default


def _dataframe_layout_kwargs() -> Dict[str, object]:
    if "width" in inspect.signature(st.dataframe).parameters:
        return {"width": "stretch"}
    return {"use_container_width": True}


def _normalized_extensions(values: Iterable[str]) -> Tuple[str, ...]:
    normalized = []
    for value in values:
        item = value.strip().lower()
        if not item:
            continue
        normalized.append(item if item.startswith(".") else f".{item}")
    return tuple(sorted(dict.fromkeys(normalized)))


def _resolved_include_extensions(profile: Profile) -> Tuple[str, ...]:
    return _normalized_extensions(
        profile.include_extensions or presets.DEFAULT_INCLUDE_EXTENSIONS
    )


def _resolved_exclude_dirs(profile: Profile) -> Tuple[str, ...]:
    merged = list(presets.DEFAULT_EXCLUDE_DIRS) + list(profile.exclude_dirs)
    return tuple(sorted(dict.fromkeys(item for item in merged if item)))


def _scan_cache_key(
    source_dir: Path,
    include_extensions: Sequence[str],
    exclude_dirs: Sequence[str],
) -> Tuple[str, Tuple[str, ...], Tuple[str, ...]]:
    return (str(source_dir.resolve()), tuple(include_extensions), tuple(exclude_dirs))


def _scan_key_id(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
) -> str:
    return sha1(repr(key).encode("utf-8")).hexdigest()[:12]


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    value = float(num_bytes)
    for unit in ("KB", "MB", "GB"):
        value /= 1024.0
        if value < 1024.0:
            return f"{value:.1f} {unit}"
    return f"{value / 1024.0:.1f} TB"


def _is_supported(scanned: ScannedFile) -> bool:
    return scanned.file_type != "unsupported"


def _count_by_file_type(files: Sequence[ScannedFile]) -> Dict[str, int]:
    counter = Counter(presets.classify_extension(f.extension) for f in files)
    return {file_type: counter.get(file_type, 0) for file_type in FILE_TYPE_ORDER}


def _duplicate_filename_groups(files: Sequence[ScannedFile]) -> Dict[str, List[str]]:
    by_name: Dict[str, List[str]] = defaultdict(list)
    for scanned in files:
        by_name[scanned.relative_path.name.lower()].append(str(scanned.relative_path))
    return {
        basename: sorted(paths)
        for basename, paths in sorted(by_name.items())
        if len(paths) >= 2
    }


def _files_table(files: Sequence[ScannedFile]) -> List[Dict[str, object]]:
    return [
        {
            "relative_path": str(scanned.relative_path),
            "file_type": scanned.file_type,
            "extension": scanned.extension,
            "size_bytes": scanned.size_bytes,
            "will_process": _is_supported(scanned),
        }
        for scanned in files
    ]


def _selection_store_key(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
) -> str:
    return repr(key)


def _default_file_included(
    scanned: ScannedFile,
    exclude_patterns: Sequence[str],
) -> bool:
    if not _is_supported(scanned):
        return False
    return not match_path_patterns(scanned.relative_path, exclude_patterns)


def _reconcile_file_selections(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    files: Sequence[ScannedFile],
    exclude_patterns: Sequence[str] = (),
) -> Dict[str, bool]:
    store = st.session_state[SESSION_KEY_FILE_SELECTIONS]
    store_key = _selection_store_key(key)
    previous = store.get(store_key, {})
    current = {
        str(scanned.relative_path): bool(
            previous.get(
                str(scanned.relative_path),
                _default_file_included(scanned, exclude_patterns),
            )
        )
        for scanned in files
    }
    store[store_key] = current
    return current


def _selection_revision(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
) -> int:
    revisions = st.session_state[SESSION_KEY_FILE_SELECTION_REVISIONS]
    return int(revisions.get(_selection_store_key(key), 0))


def _bump_selection_revision(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
) -> None:
    revisions = st.session_state[SESSION_KEY_FILE_SELECTION_REVISIONS]
    store_key = _selection_store_key(key)
    revisions[store_key] = int(revisions.get(store_key, 0)) + 1


def _record_path(record: Dict[str, object]) -> str:
    return str(record.get("relative_path", ""))


def _editor_records(value: object) -> List[Dict[str, object]]:
    if hasattr(value, "to_dict"):
        return value.to_dict("records")  # type: ignore[no-any-return, attr-defined]
    return list(value)  # type: ignore[arg-type]


def _file_review_status(scanned: ScannedFile, included: bool) -> Tuple[str, str]:
    if scanned.file_type == "unsupported":
        return (
            "unsupported",
            "Unsupported extension; visible for review and excluded by default.",
        )
    if included:
        return ("included", "Supported file selected for later packaging.")
    return ("excluded", "Supported file excluded by current review selection.")


def _review_rows(
    files: Sequence[ScannedFile],
    selections: Dict[str, bool],
) -> List[Dict[str, object]]:
    rows = []
    for scanned in files:
        relative_path = str(scanned.relative_path)
        included = bool(selections.get(relative_path, _is_supported(scanned)))
        status, notes = _file_review_status(scanned, included)
        rows.append(
            {
                "include": included,
                "file_name": scanned.relative_path.name,
                "relative_path": relative_path,
                "extension": scanned.extension or "(none)",
                "file_type": scanned.file_type,
                "size": _format_size(scanned.size_bytes),
                "size_bytes": scanned.size_bytes,
                "status": status,
                "notes": notes,
            }
        )
    return rows


def _filter_review_files(
    files: Sequence[ScannedFile],
    search_text: str,
    extensions: Sequence[str],
) -> List[ScannedFile]:
    search = search_text.strip().lower()
    extension_set = set(extensions)
    visible = []
    for scanned in files:
        extension = scanned.extension or "(none)"
        if extension_set and extension not in extension_set:
            continue
        if search:
            relative_path = str(scanned.relative_path).lower()
            file_name = scanned.relative_path.name.lower()
            if search not in relative_path and search not in file_name:
                continue
        visible.append(scanned)
    return visible


def _resolved_source_path(profile: Profile) -> Path:
    return Path(profile.default_source_folder.strip()).expanduser()


def _resolved_output_path(profile: Profile) -> Path:
    output = profile.default_output_folder.strip() or "./llm_project_exports"
    return Path(output).expanduser()


def _resolved_project_name(profile: Profile, source_dir: Path) -> str:
    return profile.project_name.strip() or source_dir.name or "project"


def _resolved_max_bundle_tokens(profile: Profile) -> int:
    return profile.max_bundle_tokens or presets.get_bundle_token_budget(
        profile.target,
        profile.mode,
    )


def _included_paths(
    files: Sequence[ScannedFile],
    selections: Dict[str, bool],
) -> List[str]:
    return [
        str(scanned.relative_path)
        for scanned in files
        if selections.get(str(scanned.relative_path), _is_supported(scanned))
    ]


def _selected_files(
    files: Sequence[ScannedFile],
    selections: Dict[str, bool],
) -> List[ScannedFile]:
    wanted = set(_included_paths(files, selections))
    return [scanned for scanned in files if str(scanned.relative_path) in wanted]


def _rough_token_estimate(files: Sequence[ScannedFile]) -> int:
    supported = [scanned for scanned in files if _is_supported(scanned)]
    return sum(max(1, scanned.size_bytes // 4) for scanned in supported)


def _rough_bundle_count(
    files: Sequence[ScannedFile],
    target: str,
    max_bundle_tokens: int,
) -> int | None:
    if target == "rag":
        return None
    supported = [scanned for scanned in files if _is_supported(scanned)]
    if not supported:
        return 0
    count = 1
    running = 0
    for scanned in supported:
        tokens = max(1, scanned.size_bytes // 4)
        if running and running + tokens > max_bundle_tokens:
            count += 1
            running = tokens
        else:
            running += tokens
    return count


def _planned_export_folder_name(profile: Profile) -> str:
    source_dir = _resolved_source_path(profile)
    project_name = _resolved_project_name(profile, source_dir)
    return safe_filename(
        f"{project_name}_{profile.target}_{profile.mode}_YYYYMMDD_HHMMSS"
    )


def _estimated_bundle_filenames(bundle_count: int | None) -> List[str]:
    if bundle_count is None:
        return []
    return [f"{index + 1:02d}_BUNDLE_{index:03d}.md" for index in range(1, bundle_count + 1)]


def _instruction_preview(
    profile: Profile,
    selected_files: Sequence[ScannedFile],
    bundle_count: int | None,
    max_bundle_tokens: int,
) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    source_dir = _resolved_source_path(profile)
    project_name = _resolved_project_name(profile, source_dir)
    total_tokens = _rough_token_estimate(selected_files)
    bundle_filenames = _estimated_bundle_filenames(bundle_count)
    ctx = InstructionContext(
        project_name=project_name,
        target=profile.target,
        mode=profile.mode,
        bundle_filenames=bundle_filenames,
        total_documents=len(selected_files),
        total_tokens=total_tokens,
        max_bundle_tokens=max_bundle_tokens,
    )
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = write_instructions(profile.target, Path(tmp_dir), ctx)
            return path.read_text(encoding="utf-8"), warnings
    except Exception as exc:  # noqa: BLE001 - preview should not block export
        warnings.append(f"Instruction preview could not be generated: {exc}")
        return "", warnings


def _preview_warnings(
    profile: Profile,
    files: Sequence[ScannedFile],
    selected_files: Sequence[ScannedFile],
) -> List[str]:
    warnings: List[str] = []
    if not selected_files:
        warnings.append("No files are included. Export will have nothing to process.")
    unsupported_selected = [
        str(scanned.relative_path)
        for scanned in selected_files
        if not _is_supported(scanned)
    ]
    if unsupported_selected:
        warnings.append(
            f"{len(unsupported_selected)} included file(s) have unsupported extensions "
            "and will be recorded as skipped."
        )
    excluded_count = len(files) - len(selected_files)
    if excluded_count:
        warnings.append(
            f"{excluded_count} discovered file(s) are excluded and will not be written "
            "to the manifest for this export."
        )
    source_dir = _resolved_source_path(profile).resolve()
    output_dir = _resolved_output_path(profile).resolve()
    try:
        output_dir.relative_to(source_dir)
        warnings.append(
            "The output folder is inside the source folder; the backend will skip "
            "that output directory during scan."
        )
    except ValueError:
        pass
    warnings.append(
        "Preview bundle counts use a quick size-based token estimate. The final "
        "export may differ after conversion."
    )
    return warnings


def _generated_file_rows(export_dir: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    if not export_dir.exists():
        return rows
    for path in sorted(export_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        rows.append(
            {
                "file": str(path.relative_to(export_dir)),
                "size": _format_size(size),
                "size_bytes": size,
            }
        )
    return rows


def _manual_upload_instructions(target: str, result: PackResult) -> List[str]:
    instruction_name = result.instruction_path.name if result.instruction_path else "00_*"
    if target == "chatgpt":
        return [
            "Create or open a ChatGPT Project.",
            "Upload the source manifest, generated Markdown bundles, and any needed files from assets/ and data/.",
            f"Open {instruction_name} and paste its instruction block into the project instructions.",
            "Upload is manual; this app does not connect to ChatGPT.",
        ]
    if target == "claude":
        return [
            "Create or open a Claude Project.",
            "Add the exported bundles, manifest, and any needed assets/data files to Project Knowledge.",
            f"Open {instruction_name} and paste its custom-instructions block into Claude's project instructions.",
            "Upload is manual; this app does not connect to Claude.",
        ]
    if target == "rag":
        return [
            "Use manifest.json or manifest.csv as the source index.",
            "Use rag_ready/chunks.jsonl as the chunk file for your local/API retrieval workflow.",
            "Use rag_ready/source_map.json to map source documents to chunk IDs.",
            "This app does not create embeddings or upload data anywhere.",
        ]
    return [
        "Upload or paste 01_SOURCE_MANIFEST.md first so the model has the source index.",
        "Upload or paste each generated 02_BUNDLE_*.md file in order.",
        f"Use the prompt in {instruction_name} before asking questions.",
        "Upload is manual; this app does not connect to any LLM provider.",
    ]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _render_sidebar() -> None:
    with st.sidebar:
        st.header("Profile")
        st.caption(f"Currently loaded: {st.session_state[SESSION_KEY_LAST_LOADED]}")

        st.subheader("Built-in templates")
        builtin_names = list_built_in_profiles()
        chosen_builtin = st.selectbox(
            "Pick a built-in to load",
            options=["(none)"] + builtin_names,
            key="builtin_selector",
        )
        if st.button("Load built-in", disabled=chosen_builtin == "(none)"):
            profile = get_built_in_profile(chosen_builtin)
            _set_profile(profile, f"built-in: {chosen_builtin}")
            st.success(f"Loaded built-in: {chosen_builtin}")
            st.rerun()

        st.divider()
        st.subheader("Saved profiles")
        try:
            saved_names = list_profiles()
        except Exception as exc:  # noqa: BLE001 - surface any storage error to the user
            saved_names = []
            st.warning(f"Could not list saved profiles: {exc}")

        if saved_names:
            chosen_saved = st.selectbox(
                "Pick a saved profile",
                options=["(none)"] + saved_names,
                key="saved_selector",
            )
            col_load, col_delete = st.columns(2)
            with col_load:
                if st.button("Load saved", disabled=chosen_saved == "(none)"):
                    try:
                        profile = load_profile(chosen_saved)
                        _set_profile(profile, f"saved: {chosen_saved}")
                        st.success(f"Loaded {chosen_saved}")
                        st.rerun()
                    except (FileNotFoundError, ValueError) as exc:
                        st.error(f"Load failed: {exc}")
            with col_delete:
                if st.button("Delete", disabled=chosen_saved == "(none)"):
                    if delete_profile(chosen_saved):
                        st.success(f"Deleted {chosen_saved}")
                        st.rerun()
                    else:
                        st.warning("Profile already gone.")
        else:
            st.caption("No saved profiles yet.")

        st.divider()
        if st.button("New blank profile"):
            _set_profile(_new_blank_profile(), "(blank)")
            st.rerun()


# ---------------------------------------------------------------------------
# Main form sections
# ---------------------------------------------------------------------------


def _render_project_setup(profile: Profile) -> None:
    st.subheader("Project setup")
    profile.profile_name = st.text_input(
        "Profile name",
        value=profile.profile_name,
        help="Used as the filename when you save.",
        key=_key("profile_name"),
    )
    profile.project_name = st.text_input(
        "Project name",
        value=profile.project_name,
        help="Defaults to the source folder name when blank.",
        key=_key("project_name"),
    )
    profile.default_source_folder = st.text_input(
        "Source folder",
        value=profile.default_source_folder,
        help="Path to the folder of source files to scan recursively.",
        key=_key("source_folder"),
    )
    profile.default_output_folder = st.text_input(
        "Output folder",
        value=profile.default_output_folder or "./llm_project_exports",
        key=_key("output_folder"),
    )


def _render_packaging(profile: Profile) -> None:
    st.subheader("Packaging target")
    targets = list(presets.TARGETS)
    modes = list(presets.MODES)

    col_target, col_mode = st.columns(2)
    with col_target:
        profile.target = st.selectbox(
            "Target",
            options=targets,
            index=_safe_index(targets, profile.target),
            key=_key("target"),
        )
    with col_mode:
        profile.mode = st.selectbox(
            "Mode",
            options=modes,
            index=_safe_index(modes, profile.mode),
            key=_key("mode"),
        )

    include_csv = st.text_input(
        "Include extensions (comma-separated, leave blank for the default set)",
        value=_list_to_csv(profile.include_extensions),
        help="Example: .md, .pdf, .html",
        key=_key("include_extensions"),
    )
    profile.include_extensions = _csv_to_list(include_csv)

    exclude_csv = st.text_input(
        "Extra exclude directories (comma-separated)",
        value=_list_to_csv(profile.exclude_dirs),
        help="Added to the built-in defaults like .git, __pycache__, etc.",
        key=_key("exclude_dirs"),
    )
    profile.exclude_dirs = _csv_to_list(exclude_csv)


def _render_advanced(profile: Profile) -> None:
    with st.expander("Advanced options (stored, not yet wired into packaging)"):
        st.caption(
            "These fields are saved with the profile and will be honored by "
            "later milestones. Today they are inert."
        )
        col_left, col_right = st.columns(2)
        with col_left:
            profile.include_assets = st.checkbox(
                "Include image / asset references",
                value=profile.include_assets,
                key=_key("include_assets"),
            )
            profile.copy_data_files = st.checkbox(
                "Copy original CSV / XLSX into data/",
                value=profile.copy_data_files,
                key=_key("copy_data_files"),
            )
            profile.include_pdf_page_headers = st.checkbox(
                "Include PDF page headers",
                value=profile.include_pdf_page_headers,
                key=_key("include_pdf_page_headers"),
            )
            profile.include_source_metadata = st.checkbox(
                "Include source metadata block",
                value=profile.include_source_metadata,
                key=_key("include_source_metadata"),
            )
        with col_right:
            profile.spreadsheet_preview_rows = int(
                st.number_input(
                    "Spreadsheet preview rows",
                    min_value=0,
                    value=int(profile.spreadsheet_preview_rows),
                    step=1,
                    key=_key("spreadsheet_preview_rows"),
                )
            )
            options = list(BUNDLE_SEPARATOR_OPTIONS)
            profile.bundle_separator_style = st.selectbox(
                "Bundle separator style",
                options=options,
                index=_safe_index(options, profile.bundle_separator_style),
                key=_key("bundle_separator_style"),
            )
            profile.create_zip = st.checkbox(
                "Create ZIP of export folder",
                value=profile.create_zip,
                key=_key("create_zip"),
            )


def _render_save(profile: Profile) -> None:
    st.subheader("Save")
    col_status, col_button = st.columns([2, 1])
    valid = False
    with col_status:
        try:
            profile.validate()
            valid = True
            st.caption(f"Profile is valid. Save name: {profile.profile_name!r}")
        except ValueError as exc:
            st.warning(str(exc))
    with col_button:
        if st.button("Save profile", disabled=not valid):
            try:
                path = save_profile(profile)
                st.success(f"Saved to {path}")
            except (OSError, ValueError) as exc:
                st.error(f"Save failed: {exc}")


def _render_scan_audit(profile: Profile) -> None:
    st.subheader("Scan audit")
    st.caption(
        "Scans only file paths and metadata. It does not convert, package, "
        "or write anything."
    )

    source_text = profile.default_source_folder.strip()
    include_extensions = _resolved_include_extensions(profile)
    exclude_dirs = _resolved_exclude_dirs(profile)

    col_scan, col_rescan = st.columns([1, 1])
    with col_scan:
        scan_clicked = st.button(
            "Scan Source Folder",
            disabled=not source_text,
            type="primary",
        )
    with col_rescan:
        rescan_clicked = st.button("Re-scan", disabled=not source_text)

    if not source_text:
        st.info("Set a source folder above, then scan it here.")
        return

    source_dir = Path(source_text).expanduser()

    if not source_dir.exists() or not source_dir.is_dir():
        if scan_clicked or rescan_clicked:
            st.error(f"Source folder does not exist or is not a directory: {source_dir}")
        return

    key = _scan_cache_key(source_dir, include_extensions, exclude_dirs)
    cache = st.session_state[SESSION_KEY_SCAN_CACHE]

    if rescan_clicked:
        cache.pop(key, None)
        scan_clicked = True

    if scan_clicked and key not in cache:
        with st.spinner("Scanning source folder..."):
            cache[key] = scan_directory(source_dir, include_extensions, exclude_dirs)

    files = cache.get(key)
    if files is None:
        st.info("Click Scan Source Folder to build the read-only audit.")
        return

    total_files = len(files)
    supported_files = sum(
        1
        for scanned in files
        if presets.classify_extension(scanned.extension) != "unsupported"
    )
    unsupported_files = total_files - supported_files
    total_size = sum(scanned.size_bytes for scanned in files)
    duplicates = _duplicate_filename_groups(files)

    metric_cols = st.columns(5)
    metric_cols[0].metric("Total files", total_files)
    metric_cols[1].metric("Supported files", supported_files)
    metric_cols[2].metric("Unsupported files", unsupported_files)
    metric_cols[3].metric("Estimated total size", _format_size(total_size))
    metric_cols[4].metric("Duplicate filenames", len(duplicates))

    if supported_files == 0:
        st.warning("No supported files were found with the current include/exclude settings.")

    st.markdown("**Exclude directories applied**")
    st.write(", ".join(exclude_dirs) if exclude_dirs else "(none)")

    counts_by_extension = Counter(scanned.extension or "(no extension)" for scanned in files)
    counts_by_type = _count_by_file_type(files)

    col_ext, col_type = st.columns(2)
    with col_ext:
        st.markdown("**Counts by extension**")
        if counts_by_extension:
            st.dataframe(
                [
                    {"extension": ext, "count": count}
                    for ext, count in sorted(counts_by_extension.items())
                ],
                hide_index=True,
                **_dataframe_layout_kwargs(),
            )
        else:
            st.caption("No files found.")
    with col_type:
        st.markdown("**Counts by file type**")
        st.dataframe(
            [
                {"file_type": file_type, "count": count}
                for file_type, count in counts_by_type.items()
            ],
            hide_index=True,
            **_dataframe_layout_kwargs(),
        )

    st.markdown("**Duplicate filenames**")
    if duplicates:
        for basename, paths in duplicates.items():
            with st.expander(f"{basename} ({len(paths)} files)"):
                for path in paths:
                    st.write(path)
    else:
        st.caption("No duplicate filenames found.")

    st.markdown("**Files**")
    st.dataframe(
        _files_table(files),
        hide_index=True,
        **_dataframe_layout_kwargs(),
        column_config={
            "relative_path": st.column_config.TextColumn("relative_path"),
            "file_type": st.column_config.TextColumn("file_type"),
            "extension": st.column_config.TextColumn("extension"),
            "size_bytes": st.column_config.NumberColumn("size_bytes", format="%d"),
            "will_process": st.column_config.CheckboxColumn("will_process", disabled=True),
        },
    )

    _render_file_review(key, files)


def _render_file_review(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    files: Sequence[ScannedFile],
) -> None:
    st.subheader("File review")

    profile = _profile()
    selections = _reconcile_file_selections(key, files, profile.exclude_files)
    st.caption(
        "Excluded supported files are saved to the profile as `exclude_files`, "
        "so a saved profile re-applies this selection on the next scan and on "
        "profile-driven exports."
    )
    included_count = sum(1 for included in selections.values() if included)
    supported_count = sum(1 for scanned in files if _is_supported(scanned))
    unsupported_count = len(files) - supported_count

    summary_cols = st.columns(4)
    summary_cols[0].metric("Discovered", len(files))
    summary_cols[1].metric("Included", included_count)
    summary_cols[2].metric("Supported", supported_count)
    summary_cols[3].metric("Unsupported", unsupported_count)

    all_extensions = sorted(
        {scanned.extension or "(none)" for scanned in files},
        key=lambda value: (value == "(none)", value),
    )
    widget_prefix = f"review_{_scan_key_id(key)}"

    col_search, col_filter = st.columns([2, 1])
    with col_search:
        search_text = st.text_input(
            "Search by file name or relative path",
            key=f"{widget_prefix}_search",
        )
    with col_filter:
        extension_filter = st.multiselect(
            "Filter by extension",
            options=all_extensions,
            key=f"{widget_prefix}_extension_filter",
        )

    visible_files = _filter_review_files(files, search_text, extension_filter)
    visible_paths = {str(scanned.relative_path) for scanned in visible_files}

    st.caption(
        f"Showing {len(visible_files)} of {len(files)} files. "
        "Filtering does not reset include selections."
    )

    col_all, col_visible, col_ext = st.columns(3)
    with col_all:
        if st.button("Include all supported files", key=f"{widget_prefix}_include_all"):
            for scanned in files:
                selections[str(scanned.relative_path)] = _is_supported(scanned)
            _bump_selection_revision(key)
            st.rerun()
        if st.button("Exclude all files", key=f"{widget_prefix}_exclude_all"):
            for scanned in files:
                selections[str(scanned.relative_path)] = False
            _bump_selection_revision(key)
            st.rerun()

    with col_visible:
        if st.button(
            "Include visible supported files",
            key=f"{widget_prefix}_include_visible",
        ):
            for scanned in visible_files:
                if _is_supported(scanned):
                    selections[str(scanned.relative_path)] = True
            _bump_selection_revision(key)
            st.rerun()
        if st.button("Exclude visible files", key=f"{widget_prefix}_exclude_visible"):
            for relative_path in visible_paths:
                selections[relative_path] = False
            _bump_selection_revision(key)
            st.rerun()

    with col_ext:
        extension_actions = st.multiselect(
            "Extension action target",
            options=all_extensions,
            key=f"{widget_prefix}_extension_action",
        )
        ext_button_cols = st.columns(2)
        with ext_button_cols[0]:
            if st.button(
                "Include by extension",
                disabled=not extension_actions,
                key=f"{widget_prefix}_include_by_extension",
            ):
                action_set = set(extension_actions)
                for scanned in files:
                    if (scanned.extension or "(none)") in action_set:
                        selections[str(scanned.relative_path)] = True
                _bump_selection_revision(key)
                st.rerun()
        with ext_button_cols[1]:
            if st.button(
                "Exclude by extension",
                disabled=not extension_actions,
                key=f"{widget_prefix}_exclude_by_extension",
            ):
                action_set = set(extension_actions)
                for scanned in files:
                    if (scanned.extension or "(none)") in action_set:
                        selections[str(scanned.relative_path)] = False
                _bump_selection_revision(key)
                st.rerun()

    edited_rows = st.data_editor(
        _review_rows(visible_files, selections),
        hide_index=True,
        key=f"{widget_prefix}_editor_{_selection_revision(key)}",
        **_dataframe_layout_kwargs(),
        column_config={
            "include": st.column_config.CheckboxColumn("include"),
            "file_name": st.column_config.TextColumn("file_name"),
            "relative_path": st.column_config.TextColumn("relative_path"),
            "extension": st.column_config.TextColumn("extension"),
            "file_type": st.column_config.TextColumn("file_type"),
            "size": st.column_config.TextColumn("size"),
            "size_bytes": st.column_config.NumberColumn(
                "size_bytes",
                format="%d",
            ),
            "status": st.column_config.TextColumn("status"),
            "notes": st.column_config.TextColumn("notes"),
        },
        disabled=[
            "file_name",
            "relative_path",
            "extension",
            "file_type",
            "size",
            "size_bytes",
            "status",
            "notes",
        ],
    )

    for record in _editor_records(edited_rows):
        relative_path = _record_path(record)
        if relative_path:
            selections[relative_path] = bool(record.get("include", False))

    profile.exclude_files = sorted(
        str(scanned.relative_path)
        for scanned in files
        if _is_supported(scanned)
        and not selections.get(str(scanned.relative_path), True)
    )

    _render_chunk_review(key, files, selections)
    _render_packaging_settings(key, files, selections)
    _render_preview_and_export(key, files, selections)


def _chunk_store(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
) -> Dict[str, Dict[str, object]]:
    return st.session_state[SESSION_KEY_CHUNK_SELECTIONS].setdefault(
        _selection_store_key(key), {}
    )


def _chunk_revision(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    relative_path: str,
) -> int:
    revisions = st.session_state[SESSION_KEY_CHUNK_REVISIONS]
    return int(revisions.get((_selection_store_key(key), relative_path), 0))


def _bump_chunk_revision(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    relative_path: str,
) -> None:
    revisions = st.session_state[SESSION_KEY_CHUNK_REVISIONS]
    revision_key = (_selection_store_key(key), relative_path)
    revisions[revision_key] = int(revisions.get(revision_key, 0)) + 1


def _chunk_preview_text(text: str, limit: int = 160) -> str:
    line = " ".join(text.split())
    return line[:limit] + ("…" if len(line) > limit else "")


def _export_chunk_selections(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    files: Sequence[ScannedFile],
    selections: Dict[str, bool],
) -> Tuple[Dict[str, List[int]], int | None, str, int]:
    """Return partial chunk selections for included files plus the chunk
    settings (budget, strategy, heading level) they were made under.

    The chunk settings come from the active profile (the review widgets bind
    to it), so a RAG export's ``chunks.jsonl`` matches what the user
    previewed even without partial selections."""
    store = _chunk_store(key)
    included = set(_included_paths(files, selections))
    partial: Dict[str, List[int]] = {}
    profile = _profile()
    budget: int | None = (
        int(profile.chunk_token_budget)
        if profile.chunk_token_budget is not None
        else None
    )
    strategy = profile.chunk_strategy
    heading_level = int(profile.chunk_heading_level)
    for relative_path, state in store.items():
        if relative_path not in included:
            continue
        selected = list(state.get("selected", []))  # type: ignore[arg-type]
        if len(selected) == int(state.get("total", 0)):  # type: ignore[arg-type]
            continue
        partial[relative_path] = [int(i) for i in selected]
        budget = int(state.get("budget", DEFAULT_CHUNK_REVIEW_TOKENS))  # type: ignore[arg-type]
        strategy = str(state.get("strategy", STRATEGY_TOKENS))
        heading_level = int(state.get("heading_level", DEFAULT_HEADING_LEVEL))  # type: ignore[arg-type]
    return partial, budget, strategy, heading_level


def _chunk_rule_patterns(profile: Profile) -> Tuple[str, ...]:
    return tuple(
        pattern.strip()
        for pattern in profile.chunk_exclude_headings
        if pattern and pattern.strip()
    )


def _render_chunk_review(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    files: Sequence[ScannedFile],
    selections: Dict[str, bool],
) -> None:
    st.subheader("Document chunk review")
    st.caption(
        "Optional: preview how an included document splits into token-sized "
        "chunks and deselect the portions you don't need. Documents without a "
        "chunk selection are exported in full. Previews convert one file at a "
        "time in a temporary workspace; nothing is written to the output folder."
    )

    profile = _profile()
    rules_csv = st.text_input(
        "Corpus chunk rules: exclude chunks whose first heading matches "
        "(comma-separated, * wildcards)",
        value=_list_to_csv(profile.chunk_exclude_headings),
        help=(
            "Applied to every document at export — no per-document clicking. "
            "Example for scraped records: url, slug, content_hash, *_html, "
            "discovered_links. Matching is case-insensitive against each "
            "chunk's first heading, so it works best with the heading "
            "strategy. A per-document chunk selection overrides these rules "
            "for that document. Saved with the profile."
        ),
        key=_key("chunk_exclude_headings"),
    )
    profile.chunk_exclude_headings = _csv_to_list(rules_csv)
    rules = _chunk_rule_patterns(profile)

    eligible = [
        scanned
        for scanned in _selected_files(files, selections)
        if _is_supported(scanned)
    ]
    store = _chunk_store(key)
    if not eligible:
        st.info("Include at least one supported file above to review its chunks.")
        return

    widget_prefix = f"chunks_{_scan_key_id(key)}"
    strategy_options = list(CHUNK_STRATEGY_LABELS)
    level_options = [1, 2, 3, 4]
    col_strategy, col_level, col_budget = st.columns([2, 1, 1])
    with col_strategy:
        strategy = st.selectbox(
            "Chunking strategy",
            options=strategy_options,
            index=_safe_index(strategy_options, profile.chunk_strategy),
            format_func=lambda value: CHUNK_STRATEGY_LABELS[value],
            key=_key("chunk_strategy"),
            help=(
                "Token budget packs paragraphs greedily up to the chunk size. "
                "Heading sections never merge content across headings — each "
                "section becomes its own chunk (split further only if it "
                "exceeds the chunk size). Use heading sections when documents "
                "have meaningful structure, e.g. converted records or manuals. "
                "Saved with the profile."
            ),
        )
        profile.chunk_strategy = strategy
    with col_level:
        if strategy == STRATEGY_HEADINGS:
            level_index = (
                level_options.index(int(profile.chunk_heading_level))
                if int(profile.chunk_heading_level) in level_options
                else DEFAULT_HEADING_LEVEL - 1
            )
            heading_level = int(
                st.selectbox(
                    "Split at heading level",
                    options=level_options,
                    index=level_index,
                    key=_key("chunk_heading_level"),
                    help=(
                        "Sections start at headings of this level or shallower; "
                        "deeper headings stay inside their section. Saved with "
                        "the profile."
                    ),
                )
            )
            profile.chunk_heading_level = heading_level
        else:
            heading_level = int(profile.chunk_heading_level)
    with col_budget:
        budget = int(
            st.number_input(
                "Chunk size (tokens)",
                min_value=50,
                value=int(profile.chunk_token_budget or DEFAULT_CHUNK_REVIEW_TOKENS),
                step=50,
                key=_key("chunk_token_budget"),
                help=(
                    "Smaller chunks give finer selection control. Changing any "
                    "chunk setting re-chunks documents and clears selections "
                    "made under different settings. Saved with the profile."
                ),
            )
        )
        profile.chunk_token_budget = budget

    stale_paths = [
        relative_path
        for relative_path, state in store.items()
        if (
            int(state.get("budget", -1)) != budget  # type: ignore[arg-type]
            or str(state.get("strategy", STRATEGY_TOKENS)) != strategy
            or int(state.get("heading_level", DEFAULT_HEADING_LEVEL)) != heading_level  # type: ignore[arg-type]
            or tuple(state.get("rules", ())) != rules  # type: ignore[arg-type]
        )
    ]
    for relative_path in stale_paths:
        del store[relative_path]
    if stale_paths:
        st.info(
            f"Cleared chunk selections for {len(stale_paths)} document(s) made "
            "under different chunk settings."
        )

    _render_corpus_chunk_audit(
        key, eligible, budget, strategy, heading_level, rules, widget_prefix
    )

    paths = [str(scanned.relative_path) for scanned in eligible]
    chosen = st.selectbox("Document", options=paths, key=f"{widget_prefix}_doc")
    scanned = next(s for s in eligible if str(s.relative_path) == chosen)
    source_root = _resolved_source_path(_profile())

    cache = st.session_state[SESSION_KEY_CHUNK_PREVIEWS]
    cache_key = (_selection_store_key(key), chosen, budget, strategy, heading_level)
    col_preview, col_refresh = st.columns([1, 1])
    preview_clicked = col_preview.button(
        "Preview chunks",
        type="primary",
        key=f"{widget_prefix}_preview",
    )
    if col_refresh.button("Refresh preview", key=f"{widget_prefix}_refresh"):
        cache.pop(cache_key, None)
        preview_clicked = True
    if preview_clicked and cache_key not in cache:
        with st.spinner(f"Converting and chunking {chosen}..."):
            cache[cache_key] = preview_document_chunks(
                scanned, source_root, budget, strategy, heading_level
            )

    preview = cache.get(cache_key)
    if isinstance(preview, DocumentChunkPreview):
        _render_chunk_editor(
            key,
            chosen,
            budget,
            strategy,
            heading_level,
            rules,
            preview,
            store,
            widget_prefix,
        )
    else:
        st.info("Click Preview chunks to convert this document and list its chunks.")

    _render_chunk_summary(key, store, widget_prefix)


def _corpus_audit_key(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    budget: int,
    strategy: str,
    heading_level: int,
    eligible: Sequence[ScannedFile],
) -> Tuple[str, int, str, int, str]:
    paths = tuple(sorted(str(scanned.relative_path) for scanned in eligible))
    return (
        _selection_store_key(key),
        budget,
        strategy,
        heading_level,
        sha1(repr(paths).encode("utf-8")).hexdigest()[:12],
    )


def _render_corpus_chunk_audit(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    eligible: Sequence[ScannedFile],
    budget: int,
    strategy: str,
    heading_level: int,
    rules: Tuple[str, ...],
    widget_prefix: str,
) -> None:
    with st.expander("Corpus chunking audit", expanded=False):
        st.caption(
            "Converts every included document and chunks it with the current "
            "settings, so you can see how the chunker behaves across the "
            "whole corpus — where boundaries land and why — and get guidance "
            "before reviewing individual documents."
        )
        audit_store = st.session_state[SESSION_KEY_CORPUS_AUDIT]
        audit_key = _corpus_audit_key(key, budget, strategy, heading_level, eligible)
        if st.button(
            f"Analyze corpus chunking ({len(eligible)} document(s))",
            key=f"{widget_prefix}_corpus",
        ):
            source_root = _resolved_source_path(_profile())
            cache = st.session_state[SESSION_KEY_CHUNK_PREVIEWS]
            progress = st.progress(0)
            previews: Dict[str, DocumentChunkPreview] = {}
            for position, scanned in enumerate(eligible, start=1):
                relative_path = str(scanned.relative_path)
                cache_key = (
                    _selection_store_key(key),
                    relative_path,
                    budget,
                    strategy,
                    heading_level,
                )
                if cache_key not in cache:
                    cache[cache_key] = preview_document_chunks(
                        scanned, source_root, budget, strategy, heading_level
                    )
                previews[relative_path] = cache[cache_key]
                progress.progress(int(position / len(eligible) * 100))
            audit_store[audit_key] = previews
            progress.empty()

        previews = audit_store.get(audit_key)
        if previews is None:
            st.caption(
                "Not analyzed yet for the current scan, selection, and chunk settings."
            )
            return
        _render_corpus_audit_results(previews, budget)

        if rules:
            all_chunks = [
                chunk
                for preview in previews.values()
                if preview.status == "ok"
                for chunk in preview.chunks
            ]
            rule_rows = []
            for pattern in rules:
                matches = sum(
                    1
                    for chunk in all_chunks
                    if match_heading_patterns(chunk.first_heading, (pattern,))
                )
                rule_rows.append({"rule": pattern, "matching_chunks": matches})
            st.markdown("**Corpus chunk rules**")
            st.dataframe(rule_rows, hide_index=True, **_dataframe_layout_kwargs())
            unmatched = [row["rule"] for row in rule_rows if not row["matching_chunks"]]
            if unmatched:
                st.warning(
                    "Rule(s) matching no chunks at the current settings: "
                    + ", ".join(repr(rule) for rule in unmatched)
                )

        tips = chunking_guidance(previews, budget, strategy, _profile().target)
        st.markdown("**Chunking guidance**")
        if tips:
            for tip in tips:
                st.info(tip)
        else:
            st.caption(
                "Nothing stood out: chunk sizes are within budget and match "
                "the current strategy well."
            )


def _render_corpus_audit_results(
    previews: Dict[str, DocumentChunkPreview],
    budget: int,
) -> None:
    converted = {
        path: preview for path, preview in previews.items() if preview.status == "ok"
    }
    failed = {
        path: preview for path, preview in previews.items() if preview.status != "ok"
    }
    all_chunks = [chunk for preview in converted.values() for chunk in preview.chunks]
    over_budget = sum(1 for chunk in all_chunks if chunk.token_estimate > budget)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Documents analyzed", len(previews))
    metric_cols[1].metric("Total chunks", len(all_chunks))
    metric_cols[2].metric(
        "Total tokens",
        f"{sum(chunk.token_estimate for chunk in all_chunks):,}",
    )
    metric_cols[3].metric("Chunks over budget", over_budget)

    if all_chunks:
        sizes = sorted(chunk.token_estimate for chunk in all_chunks)
        st.write(
            f"Chunk sizes (tokens): smallest {sizes[0]:,}, "
            f"median {sizes[len(sizes) // 2]:,}, largest {sizes[-1]:,} "
            f"against a budget of {budget:,}."
        )

        reason_counts = Counter(chunk.boundary_reason for chunk in all_chunks)
        st.markdown("**Why chunk boundaries were drawn**")
        st.dataframe(
            [
                {"boundary_reason": reason, "chunks": count}
                for reason, count in reason_counts.most_common()
            ],
            hide_index=True,
            **_dataframe_layout_kwargs(),
        )

    st.markdown("**Per-document chunking**")
    st.dataframe(
        [
            {
                "relative_path": path,
                "chunks": len(preview.chunks),
                "tokens": preview.total_tokens,
                "largest_chunk": max(
                    (chunk.token_estimate for chunk in preview.chunks), default=0
                ),
                "over_budget_chunks": sum(
                    1 for chunk in preview.chunks if chunk.token_estimate > budget
                ),
                "headings": sum(
                    len(chunk.structure.headings)
                    for chunk in preview.chunks
                    if chunk.structure
                ),
                "single_chunk": len(preview.chunks) == 1,
            }
            for path, preview in sorted(converted.items())
        ],
        hide_index=True,
        **_dataframe_layout_kwargs(),
    )
    if over_budget:
        st.warning(
            f"{over_budget} chunk(s) exceed the budget. These come from single "
            "lines (often tables or long list rows) that cannot be split at a "
            "paragraph or line boundary."
        )
    for path, preview in sorted(failed.items()):
        st.warning(f"Could not convert {path} (status: {preview.status}). {preview.notes}")


def _render_chunk_editor(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    relative_path: str,
    budget: int,
    strategy: str,
    heading_level: int,
    rules: Tuple[str, ...],
    preview: DocumentChunkPreview,
    store: Dict[str, Dict[str, object]],
    widget_prefix: str,
) -> None:
    if preview.status != "ok":
        st.warning(
            f"Could not convert {relative_path} (status: {preview.status}). "
            f"{preview.notes}"
        )
        return
    if not preview.chunks:
        st.caption("This document converted to empty content; nothing to select.")
        return

    state = store.get(relative_path)
    if state is None or int(state.get("total", -1)) != len(preview.chunks):  # type: ignore[arg-type]
        default_selected = [
            chunk.index
            for chunk in preview.chunks
            if not match_heading_patterns(chunk.first_heading, rules)
        ]
        rule_excluded = len(preview.chunks) - len(default_selected)
        if rule_excluded:
            st.info(
                f"{rule_excluded} chunk(s) default to excluded because their "
                "heading matches a corpus chunk rule. Re-include any of them "
                "to override the rules for this document."
            )
        state = {
            "budget": budget,
            "strategy": strategy,
            "heading_level": heading_level,
            "rules": list(rules),
            "selected": default_selected,
            "total": len(preview.chunks),
        }
        store[relative_path] = state
    selected_set = {int(i) for i in state["selected"]}  # type: ignore[union-attr]

    col_all, col_none = st.columns(2)
    if col_all.button("Include all chunks", key=f"{widget_prefix}_include_all_chunks"):
        state["selected"] = list(range(1, len(preview.chunks) + 1))
        _bump_chunk_revision(key, relative_path)
        st.rerun()
    if col_none.button("Exclude all chunks", key=f"{widget_prefix}_exclude_all_chunks"):
        state["selected"] = []
        _bump_chunk_revision(key, relative_path)
        st.rerun()

    if strategy == STRATEGY_HEADINGS:
        st.caption(
            f"How chunks are made: a new chunk starts at every heading of "
            f"level {heading_level} or shallower (deeper headings stay inside "
            "their section); a section bigger than the token budget is split "
            "by paragraphs, then lines. Each row shows the structure a chunk "
            "contains and why its boundary was drawn — use this to judge "
            "whether the settings suit the corpus."
        )
    else:
        st.caption(
            "How chunks are made: paragraphs are appended in order until the "
            "next paragraph would push the chunk over the token budget; a "
            "paragraph bigger than the budget on its own is split at line "
            "boundaries. Each row shows the structure a chunk contains and "
            "why its boundary was drawn — use this to judge whether the "
            "settings suit the corpus."
        )
    rows = [
        {
            "include": chunk.index in selected_set,
            "chunk": chunk.index,
            "tokens": chunk.token_estimate,
            "heading": chunk.first_heading,
            "structure": chunk.structure.describe() if chunk.structure else "",
            "boundary": chunk.boundary_reason,
            "preview": _chunk_preview_text(chunk.text),
        }
        for chunk in preview.chunks
    ]
    editor_key = (
        f"{widget_prefix}_editor_{sha1(relative_path.encode('utf-8')).hexdigest()[:8]}"
        f"_{budget}_{strategy}_{heading_level}_{_chunk_revision(key, relative_path)}"
    )
    edited_rows = st.data_editor(
        rows,
        hide_index=True,
        key=editor_key,
        **_dataframe_layout_kwargs(),
        column_config={
            "include": st.column_config.CheckboxColumn("include"),
            "chunk": st.column_config.NumberColumn("chunk", format="%d"),
            "tokens": st.column_config.NumberColumn("tokens", format="%d"),
            "heading": st.column_config.TextColumn("heading"),
            "structure": st.column_config.TextColumn("structure"),
            "boundary": st.column_config.TextColumn("boundary"),
            "preview": st.column_config.TextColumn("preview"),
        },
        disabled=["chunk", "tokens", "heading", "structure", "boundary", "preview"],
    )
    state["selected"] = sorted(
        int(record["chunk"])
        for record in _editor_records(edited_rows)
        if record.get("include")
    )

    selected_now = {int(i) for i in state["selected"]}  # type: ignore[union-attr]
    kept_tokens = sum(
        chunk.token_estimate for chunk in preview.chunks if chunk.index in selected_now
    )
    metric_cols = st.columns(3)
    metric_cols[0].metric("Chunks", len(preview.chunks))
    metric_cols[1].metric("Selected chunks", len(selected_now))
    metric_cols[2].metric(
        "Selected tokens",
        f"{kept_tokens:,} / {preview.total_tokens:,}",
    )
    if not selected_now:
        st.warning(
            "All chunks are deselected. This document will be recorded as "
            "skipped and its content omitted from the export."
        )

    with st.expander("View chunk text", expanded=False):
        for chunk in preview.chunks:
            marker = "included" if chunk.index in selected_now else "excluded"
            details = chunk.structure.describe() if chunk.structure else ""
            st.markdown(
                f"**Chunk {chunk.index}** — {chunk.token_estimate:,} tokens, "
                f"{marker} · {details} · boundary: {chunk.boundary_reason}"
            )
            st.code(chunk.text[:5000], language="markdown")


def _render_chunk_summary(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    store: Dict[str, Dict[str, object]],
    widget_prefix: str,
) -> None:
    partial = {
        relative_path: state
        for relative_path, state in store.items()
        if len(state.get("selected", [])) != int(state.get("total", 0))  # type: ignore[arg-type]
    }
    if not partial:
        st.caption("No chunk selections yet; every document exports in full.")
        return

    st.markdown("**Documents with chunk selections**")
    st.dataframe(
        [
            {
                "relative_path": relative_path,
                "selected_chunks": len(state.get("selected", [])),  # type: ignore[arg-type]
                "total_chunks": int(state.get("total", 0)),  # type: ignore[arg-type]
            }
            for relative_path, state in sorted(partial.items())
        ],
        hide_index=True,
        **_dataframe_layout_kwargs(),
    )
    if st.button("Clear all chunk selections", key=f"{widget_prefix}_clear_chunks"):
        store.clear()
        st.rerun()


def _render_packaging_settings(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    files: Sequence[ScannedFile],
    selections: Dict[str, bool],
) -> None:
    profile = _profile()
    selected_files = _selected_files(files, selections)
    default_budget = presets.get_bundle_token_budget(profile.target, profile.mode)
    rough_tokens = _rough_token_estimate(selected_files)
    widget_prefix = f"settings_{_scan_key_id(key)}"

    st.subheader("Packaging settings")
    st.caption(
        "These settings control how selected files are split for export. "
        "Token budgets are packaging targets, not official platform limits."
    )

    use_override = st.checkbox(
        "Override bundle token budget",
        value=profile.max_bundle_tokens is not None,
        help=f"Default for {profile.target} / {profile.mode}: {default_budget:,}",
        key=f"{widget_prefix}_use_max_bundle_tokens",
    )
    if use_override:
        profile.max_bundle_tokens = int(
            st.number_input(
                "Max bundle tokens",
                min_value=1,
                value=int(profile.max_bundle_tokens or default_budget),
                step=1000,
                key=f"{widget_prefix}_max_bundle_tokens",
            )
        )
    else:
        profile.max_bundle_tokens = None

    updated_budget = _resolved_max_bundle_tokens(profile)
    updated_projection = _rough_bundle_count(
        selected_files,
        profile.target,
        updated_budget,
    )
    col_target, col_default, col_current, col_projected = st.columns(4)
    col_target.metric("Target / mode", f"{profile.target} / {profile.mode}")
    col_default.metric("Default budget", f"{default_budget:,}")
    col_current.metric("Resolved budget", f"{updated_budget:,}")
    col_projected.metric(
        "Projected bundles",
        "RAG chunks" if updated_projection is None else updated_projection,
    )
    st.write(
        f"Selected files: {len(selected_files)}. "
        f"Rough selected-token estimate: {rough_tokens:,}. "
        f"Projected export shape: "
        f"{'RAG JSONL chunks' if updated_projection is None else str(updated_projection) + ' Markdown bundle(s)'}."
    )


def _render_preview_and_export(
    key: Tuple[str, Tuple[str, ...], Tuple[str, ...]],
    files: Sequence[ScannedFile],
    selections: Dict[str, bool],
) -> None:
    profile = _profile()
    selected_files = _selected_files(files, selections)
    included_paths = _included_paths(files, selections)
    included_count = len(selected_files)
    skipped_count = len(files) - included_count
    max_bundle_tokens = _resolved_max_bundle_tokens(profile)
    bundle_count = _rough_bundle_count(
        selected_files,
        profile.target,
        max_bundle_tokens,
    )
    chunk_selections, chunk_token_budget, chunk_strategy, chunk_heading_level = (
        _export_chunk_selections(key, files, selections)
    )
    warnings = _preview_warnings(profile, files, selected_files)
    if chunk_selections:
        warnings.append(
            f"{len(chunk_selections)} document(s) have partial chunk selections; "
            "their content will be trimmed at export."
        )
    if profile.target == "rag" and chunk_token_budget is not None:
        warnings.append(
            "RAG chunks.jsonl will use the chunk review settings: "
            f"{chunk_token_budget:,} tokens per chunk, "
            f"{CHUNK_STRATEGY_LABELS.get(chunk_strategy, chunk_strategy)} strategy."
        )
    chunk_rules = _chunk_rule_patterns(profile)
    if chunk_rules:
        warnings.append(
            f"Corpus chunk rules active ({len(chunk_rules)} pattern(s)): chunks "
            "whose first heading matches are excluded from every document "
            "without a per-document chunk selection."
        )
    instruction_preview, instruction_warnings = _instruction_preview(
        profile,
        selected_files,
        bundle_count,
        max_bundle_tokens,
    )
    warnings.extend(instruction_warnings)

    st.subheader("Preview")
    st.caption(
        "This is a planning preview from the current scan and file selections. "
        "The export button below performs the real conversion and bundling."
    )

    metric_cols = st.columns(5)
    metric_cols[0].metric("Included files", included_count)
    metric_cols[1].metric("Skipped files", skipped_count)
    metric_cols[2].metric(
        "Estimated bundles",
        "RAG export" if bundle_count is None else bundle_count,
    )
    metric_cols[3].metric("Target / mode", f"{profile.target} / {profile.mode}")
    metric_cols[4].metric("Max bundle tokens", f"{max_bundle_tokens:,}")

    st.markdown("**Output folder name**")
    st.code(_planned_export_folder_name(profile), language="text")

    if warnings:
        with st.expander("Warnings", expanded=True):
            for warning in warnings:
                st.warning(warning)

    if instruction_preview:
        with st.expander("Instruction file preview", expanded=False):
            st.code(instruction_preview, language="markdown")

    st.subheader("Export")
    st.caption(
        "Creates local files only. Nothing is uploaded to ChatGPT, Claude, "
        "or any other LLM provider."
    )
    if st.button(
        "Create LLM Project Bundles",
        type="primary",
        disabled=included_count == 0,
        key=f"export_{_scan_key_id(key)}",
    ):
        _run_export(
            profile,
            included_paths,
            included_count,
            chunk_selections=chunk_selections,
            chunk_token_budget=chunk_token_budget,
            chunk_strategy=chunk_strategy,
            chunk_heading_level=chunk_heading_level,
            chunk_exclude_headings=list(chunk_rules),
        )

    last_result = st.session_state.get(SESSION_KEY_LAST_EXPORT_RESULT)
    if isinstance(last_result, PackResult):
        _render_export_result(profile.target, last_result)


def _run_export(
    profile: Profile,
    included_paths: Sequence[str],
    included_count: int,
    *,
    chunk_selections: Dict[str, List[int]] | None = None,
    chunk_token_budget: int | None = None,
    chunk_strategy: str = STRATEGY_TOKENS,
    chunk_heading_level: int = DEFAULT_HEADING_LEVEL,
    chunk_exclude_headings: List[str] | None = None,
) -> None:
    source_dir = _resolved_source_path(profile)
    output_dir = _resolved_output_path(profile)
    project_name = _resolved_project_name(profile, source_dir)
    max_bundle_tokens = _resolved_max_bundle_tokens(profile)

    progress_bar = st.progress(0)
    status_placeholder = st.empty()
    log_placeholder = st.empty()
    progress_state = {"file_events": 0}
    messages: List[str] = []

    def on_progress(event: ProgressEvent) -> None:
        if event.message:
            messages.append(event.message)
            log_placeholder.code("\n".join(messages[-12:]), language="text")
            status_placeholder.info(event.message)
        if event.kind == "file_start":
            progress_state["file_events"] += 1
            percent = min(
                95,
                int((progress_state["file_events"] / max(1, included_count)) * 90),
            )
            progress_bar.progress(percent)
        elif event.kind in {"bundle_written", "manifest_start", "rag_written"}:
            progress_bar.progress(95)
        elif event.kind == "complete":
            progress_bar.progress(100)

    try:
        result = run_packaging_job(
            source_dir=source_dir,
            output_dir=output_dir,
            project_name=project_name,
            target=profile.target,
            mode=profile.mode,
            max_bundle_tokens=max_bundle_tokens,
            include_extensions=_resolved_include_extensions(profile),
            exclude_dirs=_resolved_exclude_dirs(profile),
            included_files=included_paths,
            chunk_selections=chunk_selections or None,
            chunk_token_budget=chunk_token_budget,
            chunk_strategy=chunk_strategy,
            chunk_heading_level=chunk_heading_level,
            chunk_exclude_headings=chunk_exclude_headings or None,
            progress_callback=on_progress,
        )
    except Exception as exc:  # noqa: BLE001 - show top-level export failures in the UI
        progress_bar.progress(100)
        st.session_state[SESSION_KEY_LAST_EXPORT_RESULT] = None
        st.error(f"Export failed: {exc}")
        return

    st.session_state[SESSION_KEY_LAST_EXPORT_RESULT] = result
    if result.failed_count:
        st.warning(
            f"Export completed with {result.failed_count} failed file(s). "
            "Check the manifest for details."
        )
    else:
        st.success("Export complete.")


def _render_export_result(target: str, result: PackResult) -> None:
    st.subheader("Export result")
    summary_cols = st.columns(4)
    summary_cols[0].metric("Recorded files", result.processed_count)
    summary_cols[1].metric("Failed", result.failed_count)
    summary_cols[2].metric("Skipped", result.skipped_count)
    summary_cols[3].metric("Estimated tokens", f"{result.total_token_estimate:,}")

    st.markdown("**Export folder**")
    st.code(str(result.export_dir), language="text")
    if os.name == "nt" and st.button(
        "Open export folder in Explorer",
        key=f"open_export_{str(result.export_dir)}",
    ):
        try:
            os.startfile(result.export_dir)  # type: ignore[attr-defined]
        except OSError as exc:
            st.warning(f"Could not open export folder: {exc}")

    rows = _generated_file_rows(result.export_dir)
    if rows:
        st.markdown("**Generated files**")
        st.dataframe(rows, hide_index=True, **_dataframe_layout_kwargs())

    if result.warnings:
        with st.expander("Backend warnings", expanded=True):
            for warning in result.warnings:
                st.warning(warning)
    if result.errors:
        with st.expander("Backend errors", expanded=True):
            for error in result.errors:
                st.error(error)

    st.markdown("**Manual upload instructions**")
    for index, item in enumerate(_manual_upload_instructions(target, result), start=1):
        st.write(f"{index}. {item}")

    if result.instruction_path and result.instruction_path.exists():
        with st.expander("Generated instruction file", expanded=False):
            st.code(
                result.instruction_path.read_text(encoding="utf-8"),
                language="markdown",
            )


def _render_status() -> None:
    st.subheader("Status")
    st.info(
        "The UI creates local export folders through the same backend used by "
        "the CLI. Uploads remain manual; this app does not automate LLM logins, "
        "browser actions, OCR, embeddings, or remote storage."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    _ensure_session_state()

    st.title(PAGE_TITLE)
    st.caption("Local-only project context packager. Preview and export stay on this machine.")

    _render_sidebar()
    profile = _profile()
    _render_project_setup(profile)
    _render_packaging(profile)
    _render_advanced(profile)
    _render_save(profile)
    _render_scan_audit(profile)
    _render_status()


if __name__ == "__main__":
    main()
