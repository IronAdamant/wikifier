"""Event stream over the real update-maps pipeline (``update-maps --stream``).

``generate_update_events`` runs :func:`wikifier.api.run_full_update` on a worker
thread and yields ``ProgressEvent_v1`` dicts as it goes:

  start → scope_applied → file_parsed (one per parsed file) → [partial_ready] → complete

The map is persisted exactly as by a normal update-maps. Budgets (``max_files``,
``time_budget_ms``, ``token_budget`` ≈ files) produce ``partial_ready`` with
``map_complete=false``; running again resumes, because already-parsed files are
no longer dirty. ``resume_from`` is accepted for compatibility and not needed.
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional, Union

from .api import run_full_update
from .contracts import M2_CONTRACTS_VERSION, ScopeSpec_v1, create_progress_event
from .paths import resolve_root

_DONE = object()


def generate_update_events(
    root: Optional[Path] = None,
    scope: Optional[Union[Dict[str, Any], ScopeSpec_v1]] = None,
    force_full: bool = False,
    run_id: Optional[str] = None,
    resume_from: Optional[str] = None,
    time_budget_ms: Optional[int] = None,
    token_budget: Optional[int] = None,
    max_files: Optional[int] = None,
    format: str = "full",
    verbose: bool = False,
    directory: Optional[str] = None,
    **kwargs: Any,
) -> Iterator[Dict[str, Any]]:
    """Yield progress events while the real pipeline updates the map."""
    root = Path(root).resolve() if root is not None else resolve_root()
    spec = scope if isinstance(scope, ScopeSpec_v1) else ScopeSpec_v1.from_dict(scope or {})
    directory = directory or spec.directory
    budget = min(b for b in (max_files, token_budget) if b) if (max_files or token_budget) else None
    run_id = run_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    provenance = {"actor": kwargs.get("actor", "update-maps.stream"), "session_id": kwargs.get("session_id")}

    yield create_progress_event(
        "start", run_id, scope=spec, provenance=provenance,
        payload={"force_full": bool(force_full), "contracts_version": M2_CONTRACTS_VERSION, "format": format},
        diagnostics={"resume_from": resume_from, "note": "re-running resumes; resume tokens are not required"},
    )
    yield create_progress_event(
        "scope_applied", run_id, scope=spec, provenance=provenance,
        payload={"effective_directory": directory, "max_files": budget, "time_budget_ms": time_budget_ms},
    )

    events: "queue.Queue[Any]" = queue.Queue()
    outcome: Dict[str, Any] = {}

    def worker() -> None:
        try:
            outcome["result"] = run_full_update(
                root=root,
                force_full=force_full,
                directory=directory,
                max_files=budget,
                time_budget_s=(time_budget_ms / 1000.0) if time_budget_ms else None,
                progress=events.put,
            )
        except BaseException as exc:  # surfaced in the complete event below
            outcome["error"] = exc
        finally:
            events.put(_DONE)

    thread = threading.Thread(target=worker, name="wikifier-update-stream", daemon=True)
    thread.start()
    while True:
        item = events.get()
        if item is _DONE:
            break
        if format != "summary":
            yield create_progress_event(
                "file_parsed", run_id, scope=spec, provenance={**provenance, "file": item["file"]},
                payload=item, checkpoint_token=f"after:file:{item['file']}",
            )
    thread.join()

    if "error" in outcome:
        exc = outcome["error"]
        yield create_progress_event(
            "complete", run_id, scope=spec, provenance=provenance, resumable=True,
            payload={"success": False, "error": f"{type(exc).__name__}: {exc}"},
        )
        return
    result = outcome["result"]
    summary = {
        "success": bool(result.get("success")),
        "error": result.get("error"),
        "files_parsed": result.get("files_parsed"),
        "files_to_reparse": result.get("files_to_reparse"),
        "files_skipped": result.get("files_skipped"),
        "edges_persisted": result.get("edges_persisted"),
        "map_complete": result.get("map_complete"),
        "map_coverage": result.get("map_coverage"),
        "acs_version": (result.get("map_coverage") or {}).get("acs_version"),
    }
    if not result.get("map_complete"):
        yield create_progress_event(
            "partial_ready", run_id, scope=spec, provenance=provenance,
            payload={"partial_result": summary, "continuation": "run update-maps again with the same scope"},
            checkpoint_token=f"partial:{run_id}",
        )
    yield create_progress_event(
        "complete", run_id, scope=spec, provenance={**provenance, "completed": True},
        payload=summary, resumable=not result.get("map_complete"),
        checkpoint_token=f"final:{run_id}:{result.get('files_parsed')}",
    )


def run_update_stream(
    root: Optional[Path] = None,
    scope: Optional[Union[Dict[str, Any], ScopeSpec_v1]] = None,
    force_full: bool = False,
    run_id: Optional[str] = None,
    resume_from: Optional[str] = None,
    time_budget_ms: Optional[int] = None,
    token_budget: Optional[int] = None,
    max_files: Optional[int] = None,
    format: str = "full",
    verbose: bool = False,
    directory: Optional[str] = None,
    **kwargs: Any,
) -> Iterable[Dict[str, Any]]:
    """Public streaming update-maps (see :func:`generate_update_events`)."""
    return generate_update_events(
        root=root, scope=scope, force_full=force_full, run_id=run_id, resume_from=resume_from,
        time_budget_ms=time_budget_ms, token_budget=token_budget, max_files=max_files,
        format=format, verbose=verbose, directory=directory, **kwargs,
    )
