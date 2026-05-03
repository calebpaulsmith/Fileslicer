"""llm_project_packer — Convert a folder of mixed source files into upload-ready
Markdown bundles for ChatGPT Projects, Claude Projects, generic LLM chats,
or simple RAG workflows.
"""

__version__ = "1.0.0"

from .pipeline import PackResult, ProgressEvent, run_packaging_job

__all__ = [
    "PackResult",
    "ProgressEvent",
    "run_packaging_job",
]
