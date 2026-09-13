"""Offline P&ID intake adapter.

The adapter is the only entry point for P&ID extraction inside AirBench.  It
receives already-framed page bytes from the File Intake Layer (never a host
path or container), runs the local extraction pipeline, and returns a typed
``PIDRecord``.  It is offline-only: it never downloads weights or OCR models;
a missing artifact or dependency returns a typed ``PidAdapterError``.

The output is untrusted evidence and candidate graph fragments.  It does not
mutate the World Model, task state, or approval state.
"""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from contracts import Clearance, Taint

from .records import PIDRecord, PidComponent, PidRelation

DEFAULT_LEGEND_NAME = "Refinery_PSU_Taxonomy_v1"
_REQUIRED_MODULES = ("cv2", "numpy", "ultralytics", "networkx", "skimage")


class PidAdapterError(RuntimeError):
    """A stable, non-content-bearing P&ID adapter failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class PidIntakeAdapter:
    name = "airbench.pid.adapter"
    version = "1.0"

    def __init__(
        self,
        *,
        weights_path: str | Path | None = None,
        legend_path: str | Path | None = None,
        legend_id: str = DEFAULT_LEGEND_NAME,
    ) -> None:
        self._weights_path = Path(weights_path) if weights_path is not None else None
        self._legend_path = Path(legend_path) if legend_path is not None else None
        self.legend_id = legend_id

    def _resolved_weights(self) -> Path:
        if self._weights_path is not None:
            return self._weights_path
        from .config import SYMBOL_WEIGHTS_PATH

        return SYMBOL_WEIGHTS_PATH

    def availability(self) -> tuple[bool, str]:
        """Return whether the local pipeline can run, with a reason if not."""
        missing = [module for module in _REQUIRED_MODULES if importlib.util.find_spec(module) is None]
        if missing:
            return False, f"local vision dependencies are missing: {', '.join(missing)}"
        if not self._resolved_weights().is_file():
            return False, "local P&ID detector weights are missing (downloads are disabled)"
        return True, ""

    def process(
        self,
        *,
        page_bytes: bytes,
        media_type: str,
        task_id: str,
        intake_id: str,
        revision_id: str,
        source_ref: str,
        content_hash: str,
        clearance: Clearance,
        taint: Taint,
        workspace: str | Path,
    ) -> PIDRecord:
        if not task_id or not intake_id or not revision_id or not source_ref:
            raise PidAdapterError("invalid_identity", "P&ID extraction identity is required")
        if not media_type.startswith("image/"):
            raise PidAdapterError("unsupported_media", "the P&ID adapter consumes an intake-produced page image")
        if hashlib.sha256(page_bytes).hexdigest() != content_hash:
            raise PidAdapterError("content_hash_mismatch", "the P&ID page content hash does not match")
        if taint == Taint.clean:
            raise PidAdapterError("clean_input", "intake page content must remain untrusted")

        available, reason = self.availability()
        if not available:
            raise PidAdapterError("adapter_unavailable", reason)

        work_root = Path(workspace).resolve()
        work_root.mkdir(parents=True, exist_ok=True)
        output_dir = work_root / "pid"
        suffix = ".png" if media_type == "image/png" else ".img"
        temporary = Path(tempfile.mkdtemp(dir=work_root, prefix="pid-src-"))
        source = temporary / f"page{suffix}"
        try:
            source.write_bytes(page_bytes)
            topology = self._run_pipeline(source, output_dir)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

        return self._to_record(
            topology, output_dir=output_dir, task_id=task_id, intake_id=intake_id,
            revision_id=revision_id, source_ref=source_ref, content_hash=content_hash,
            media_type=media_type, clearance=clearance, taint=taint,
        )

    def _run_pipeline(self, source: Path, output_dir: Path) -> Mapping[str, Any]:
        try:
            from .pipeline import PIDPipeline
        except ImportError as exc:  # pragma: no cover - depends on local deps
            raise PidAdapterError("adapter_unavailable", "the local P&ID pipeline could not be imported") from exc
        pipeline = PIDPipeline(custom_legend=self._legend_path, weights_path=str(self._resolved_weights()))
        try:
            return pipeline.process_image(image_path=source, output_dir=output_dir)
        except PidAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - internal failure must be typed, never leak content
            raise PidAdapterError("extraction_failed", "the P&ID extraction pipeline failed") from exc

    def _to_record(
        self,
        topology: Mapping[str, Any],
        *,
        output_dir: Path,
        task_id: str,
        intake_id: str,
        revision_id: str,
        source_ref: str,
        content_hash: str,
        media_type: str,
        clearance: Clearance,
        taint: Taint,
    ) -> PIDRecord:
        components = tuple(
            PidComponent(
                component_id=str(symbol.get("id", "")),
                label=str(symbol.get("label", "general")),
                tag=(str(symbol["tag"]) if symbol.get("tag") else None),
                bbox=_bbox(symbol.get("bbox")),
                confidence=_confidence(symbol.get("confidence")),
            )
            for symbol in topology.get("symbols", [])
        )
        relations = tuple(
            PidRelation(
                relation_id=str(edge.get("id", f"line_{index + 1}")),
                source=str(edge.get("source", "")),
                target=str(edge.get("target", "")),
                relation=str(edge.get("edge_label", "solid")),
                confidence=1.0,
            )
            for index, edge in enumerate(topology.get("edges", []))
        )
        texts = tuple(
            {"text": str(item.get("text", "")), "bbox": list(_bbox(item.get("bbox")))}
            for item in topology.get("texts", [])
        )
        stem = source_ref.replace("/", "_").replace(":", "_")[-80:] or "pid"
        graphml = output_dir / f"{stem}_generated.graphml"
        json_ref = output_dir / f"{stem}_graph.json"
        return PIDRecord(
            task_id=task_id, intake_id=intake_id, revision_id=revision_id, source_ref=source_ref,
            content_hash=content_hash, media_type=media_type, clearance=clearance, taint=taint,
            components=components, relations=relations, texts=texts, legend_id=self.legend_id,
            adapter_version=self.version,
            graphml_ref=(str(graphml) if graphml.is_file() else None),
            json_ref=(str(json_ref) if json_ref.is_file() else None),
        )


def _bbox(value: Any) -> tuple[float, float, float, float]:
    if not isinstance(value, Sequence) or len(value) != 4:
        return (0.0, 0.0, 0.0, 0.0)
    try:
        return tuple(float(item) for item in value)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return (0.0, 0.0, 0.0, 0.0)


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


__all__ = ["DEFAULT_LEGEND_NAME", "PidAdapterError", "PidIntakeAdapter"]
