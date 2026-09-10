"""AirBench Node local server entrypoint.

Reads configuration from environment variables or a YAML config file signed
with the node signing key, performs startup asset verification, emits a
``node.started`` ledger event, and binds the uvicorn process.  The module is
a thin shell: all authority flows through the orchestrator; this file only
resolves configuration and wires together the components.

Environment variables (all required unless a config file is supplied):

  AIRBENCH_NODE_IDENTITY       Stable identifier for this node (e.g. ``node.refinery.local``).
  AIRBENCH_BEARER_TOKEN        Bearer token clients must present in ``Authorization: Bearer <token>``.
  AIRBENCH_DOMAIN_PACK_REF     Canonical reference for the loaded domain pack (e.g. ``pack.refinery.v0``).
  AIRBENCH_CLEARANCE           Clearance context for this node (``public|internal|restricted|secret``).
  AIRBENCH_SUBJECT             Authenticated subject name for single-principal deployments.
  AIRBENCH_HOST                Bind host (default ``127.0.0.1``).
  AIRBENCH_PORT                Bind port (default ``8765``).
  AIRBENCH_LEDGER_PATH         Path for the SQLite ledger (omit for in-memory).
  AIRBENCH_SIGNING_KEY_PATH    Path to the 32-byte HMAC-SHA256 signing key file (optional).
  AIRBENCH_BUNDLE_MANIFEST_PATH Path to the signed offline bundle manifest (optional).
  AIRBENCH_BUNDLE_ROOT          Root directory used to resolve manifest asset paths (optional).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from contracts import (
    Clearance,
    EventLedger,
    Orchestrator,
    SQLiteLedgerStore,
)
from contracts.models import NODE_PROTOCOL_VERSION
from .api import NodeApiConfig, NodeApiService, create_app
from .bundle import BundleManifest, StartupVerifier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Startup configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NodeServerConfig:
    """Validated configuration for one AirBench Node process."""

    node_identity: str
    bearer_token: str
    domain_pack_ref: str
    clearance: Clearance
    subject: str
    host: str = "127.0.0.1"
    port: int = 8765
    ledger_path: str | None = None
    signing_key_path: str | None = None
    bundle_manifest_path: str | None = None
    bundle_root: str | None = None

    def __post_init__(self) -> None:
        for name in ("node_identity", "bearer_token", "domain_pack_ref", "subject"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"NodeServerConfig.{name} is required and must be a non-empty string")
        if not isinstance(self.port, int) or not (1 <= self.port <= 65535):
            raise ValueError("NodeServerConfig.port must be an integer in 1-65535")

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "NodeServerConfig":
        """Build a config from environment variables."""
        def _require(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                raise EnvironmentError(
                    f"Required environment variable {name} is not set. "
                    "See airbench.node.server module docstring for the full list."
                )
            return value

        try:
            clearance = Clearance(os.environ.get("AIRBENCH_CLEARANCE", "internal").strip())
        except ValueError as exc:
            raise EnvironmentError(
                "AIRBENCH_CLEARANCE must be one of: public, internal, restricted, secret"
            ) from exc

        port_raw = os.environ.get("AIRBENCH_PORT", "8765").strip()
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise EnvironmentError("AIRBENCH_PORT must be an integer") from exc

        return cls(
            node_identity=_require("AIRBENCH_NODE_IDENTITY"),
            bearer_token=_require("AIRBENCH_BEARER_TOKEN"),
            domain_pack_ref=_require("AIRBENCH_DOMAIN_PACK_REF"),
            clearance=clearance,
            subject=_require("AIRBENCH_SUBJECT"),
            host=os.environ.get("AIRBENCH_HOST", "127.0.0.1").strip(),
            port=port,
            ledger_path=os.environ.get("AIRBENCH_LEDGER_PATH", "").strip() or None,
            signing_key_path=os.environ.get("AIRBENCH_SIGNING_KEY_PATH", "").strip() or None,
            bundle_manifest_path=os.environ.get("AIRBENCH_BUNDLE_MANIFEST_PATH", "").strip() or None,
            bundle_root=os.environ.get("AIRBENCH_BUNDLE_ROOT", "").strip() or None,
        )

    @classmethod
    def from_yaml(cls, path: Path, signing_key: bytes | None = None) -> "NodeServerConfig":
        """Load config from a YAML file, verifying HMAC if a key is supplied."""
        raw = path.read_bytes()
        # Optional: if a ``signature`` key is present in the file, verify it.
        try:
            parsed: dict[str, Any] = yaml.safe_load(raw.decode("utf-8")) or {}
        except (yaml.YAMLError, UnicodeDecodeError) as exc:
            raise ValueError(f"Config file {path} is not valid YAML: {exc}") from exc

        if signing_key is not None:
            import hmac as _hmac
            expected_sig = parsed.pop("signature", None)
            if not isinstance(expected_sig, str):
                raise ValueError("Signed config file is missing a 'signature' field")
            payload_bytes = yaml.dump({k: v for k, v in parsed.items()}, sort_keys=True).encode()
            actual_sig = _hmac.new(signing_key, payload_bytes, hashlib.sha256).hexdigest()
            if not _hmac.compare_digest(expected_sig, actual_sig):
                raise ValueError("Config file signature does not match the provided signing key")

        try:
            clearance = Clearance(str(parsed.get("clearance", "internal")).strip())
        except ValueError as exc:
            raise ValueError("Config.clearance must be one of: public, internal, restricted, secret") from exc

        return cls(
            node_identity=str(parsed.get("node_identity", "")),
            bearer_token=str(parsed.get("bearer_token", "")),
            domain_pack_ref=str(parsed.get("domain_pack_ref", "")),
            clearance=clearance,
            subject=str(parsed.get("subject", "")),
            host=str(parsed.get("host", "127.0.0.1")),
            port=int(parsed.get("port", 8765)),
            ledger_path=str(parsed["ledger_path"]) if parsed.get("ledger_path") else None,
            signing_key_path=str(parsed["signing_key_path"]) if parsed.get("signing_key_path") else None,
            bundle_manifest_path=str(parsed["bundle_manifest_path"]) if parsed.get("bundle_manifest_path") else None,
            bundle_root=str(parsed["bundle_root"]) if parsed.get("bundle_root") else None,
        )


# ---------------------------------------------------------------------------
# Startup check
# ---------------------------------------------------------------------------

@dataclass
class StartupCheckResult:
    """Summary of the pre-bind startup check."""

    passed: bool
    checks: list[dict[str, str]] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append({"name": name, "status": status, "detail": detail})

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": self.checks}


def run_startup_checks(config: NodeServerConfig) -> StartupCheckResult:
    """Verify the node is ready to accept requests.

    Checks performed (all non-fatal individually, but collectively determine
    ``passed``):

    * Config completeness — all required fields are non-empty strings.
    * Ledger path — if specified, the directory is writable.
    * Signing key — if specified, the key file is readable and is exactly 32 bytes.
    * Protocol version — the expected version constant is importable.

    Returns a :class:`StartupCheckResult` with per-check detail.  A caller
    that wants hard failure should raise on ``not result.passed``.
    """
    failed = False
    result = StartupCheckResult(passed=True)

    # 1. Config completeness
    for name in ("node_identity", "bearer_token", "domain_pack_ref", "subject"):
        value = getattr(config, name)
        if isinstance(value, str) and value.strip():
            result.add(f"config.{name}", "ok")
        else:
            result.add(f"config.{name}", "failed", f"{name} is empty or missing")
            failed = True

    # 2. Ledger path writability
    if config.ledger_path:
        ledger_dir = Path(config.ledger_path).parent
        if ledger_dir.exists() and os.access(str(ledger_dir), os.W_OK):
            result.add("ledger.path", "ok", str(config.ledger_path))
        else:
            result.add("ledger.path", "failed", f"Ledger directory {ledger_dir} is not writable")
            failed = True
    else:
        result.add("ledger.path", "ok", "in-memory (no persistence)")

    # 3. Signing key
    if config.signing_key_path:
        key_path = Path(config.signing_key_path)
        if key_path.exists():
            key_bytes = key_path.read_bytes()
            if len(key_bytes) == 32:
                result.add("signing_key", "ok", str(key_path))
            else:
                result.add("signing_key", "failed", f"Signing key is {len(key_bytes)} bytes; expected 32")
                failed = True
        else:
            result.add("signing_key", "failed", f"Signing key file not found: {key_path}")
            failed = True
    else:
        result.add("signing_key", "ok", "not configured (pack verification uses the node signing key from env)")

    # 4. Protocol version
    try:
        result.add("protocol.version", "ok", NODE_PROTOCOL_VERSION)
    except Exception as exc:  # pragma: no cover
        result.add("protocol.version", "failed", str(exc))
        failed = True

    # 5. Offline bundle integrity. A configured bundle is a deployment
    # boundary: it must be present, signed, and fully verified before the
    # process is allowed to bind.
    if config.bundle_manifest_path:
        manifest_path = Path(config.bundle_manifest_path)
        signing_key: bytes | None = None
        if config.signing_key_path:
            try:
                signing_key = Path(config.signing_key_path).read_bytes()
            except OSError as exc:
                result.add("bundle.manifest", "failed", f"could not read signing key: {exc}")
                failed = True
        else:
            result.add("bundle.signature", "failed", "a signing key is required when bundle verification is configured")
            failed = True
        try:
            manifest = BundleManifest.from_file(manifest_path)
            bundle_root = Path(config.bundle_root) if config.bundle_root else manifest_path.parent
            verification = StartupVerifier(
                manifest,
                bundle_root=bundle_root,
                signing_key=signing_key,
            ).verify()
            if verification.passed:
                result.add("bundle.manifest", "ok", f"verified {manifest.bundle_id} {manifest.bundle_version}")
            else:
                result.add("bundle.manifest", "failed", json.dumps(verification.to_dict(), sort_keys=True))
                failed = True
        except (OSError, TypeError, ValueError) as exc:
            result.add("bundle.manifest", "failed", str(exc))
            failed = True
    else:
        result.add("bundle.manifest", "ok", "not configured")

    result.passed = not failed
    return result


# ---------------------------------------------------------------------------
# Ledger factory
# ---------------------------------------------------------------------------

def _build_ledger(config: NodeServerConfig) -> EventLedger:
    """Create the appropriate ledger based on config."""
    if config.ledger_path:
        key_bytes = b""
        if config.signing_key_path:
            key_path = Path(config.signing_key_path)
            if key_path.exists():
                key_bytes = key_path.read_bytes()
        return SQLiteLedgerStore(config.ledger_path, key_bytes)  # type: ignore[return-value]
    return EventLedger()


# ---------------------------------------------------------------------------
# Node start ledger event
# ---------------------------------------------------------------------------

def _write_node_started(
    config: NodeServerConfig,
    checks: StartupCheckResult,
    *,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """Write a ``node.started`` sovereignty evidence record to a JSON sidecar.

    The main ledger is task-scoped and cannot accept lifecycle events before
    ``task.created``.  Following the M9 pattern, node-lifecycle evidence is
    written as a separate signed JSON file that an offline verifier can read
    without replaying the task ledger.

    Returns the evidence payload dict so callers can include it in the API
    config's ``sovereignty_evidence_ref``.
    """
    from datetime import datetime, timezone

    payload: dict[str, Any] = {
        "event_type": "node.started",
        "node_identity": config.node_identity,
        "protocol_version": NODE_PROTOCOL_VERSION,
        "clearance": config.clearance.value,
        "domain_pack_ref": config.domain_pack_ref,
        "host": config.host,
        "port": config.port,
        "ledger_path": config.ledger_path or "in-memory",
        "startup_checks": checks.as_dict(),
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_dir / f"node_started_{config.node_identity.replace('.', '_')}.json"
        evidence_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        logger.info("Node startup evidence written to %s", evidence_path)
    return payload


# ---------------------------------------------------------------------------
# Application factory (for tests and programmatic use)
# ---------------------------------------------------------------------------

def build_node_app(
    config: NodeServerConfig,
    *,
    skip_startup_check: bool = False,
    evidence_dir: Path | None = None,
):
    """Wire the node components and return a FastAPI application.

    Parameters
    ----------
    config:
        Validated ``NodeServerConfig``.
    skip_startup_check:
        Set ``True`` in tests that supply a pre-configured in-memory ledger
        and do not want the startup check to block them.
    evidence_dir:
        Directory to write the ``node.started`` sovereignty evidence JSON sidecar.
        Defaults to the parent of ``config.ledger_path`` when set, otherwise
        the current working directory.

    Raises
    ------
    RuntimeError
        If the startup check fails and ``skip_startup_check`` is ``False``.
    """
    checks = run_startup_checks(config)
    if not skip_startup_check and not checks.passed:
        details = "; ".join(
            f"{c['name']}: {c['detail']}" for c in checks.checks if c["status"] != "ok"
        )
        raise RuntimeError(f"Node startup check failed — {details}")

    ledger = _build_ledger(config)

    # Write node-started sovereignty evidence (sidecar JSON, not the task ledger)
    if evidence_dir is None and config.ledger_path:
        evidence_dir = Path(config.ledger_path).parent
    _write_node_started(config, checks, evidence_dir=evidence_dir)

    orchestrator = Orchestrator(ledger)

    # The handshake_ledger_event_ref is the head of the ledger at the moment of
    # binding — for a fresh node this will be the empty-ledger sentinel.
    head = ledger.head_hash or "ledger.empty"

    api_config = NodeApiConfig(
        node_identity=config.node_identity,
        protocol_version=NODE_PROTOCOL_VERSION,
        clearance_context=config.clearance,
        authenticated_subject=config.subject,
        domain_pack_ref=config.domain_pack_ref,
        bearer_token=config.bearer_token,
        handshake_ledger_event_ref=head,
        sovereignty_evidence_ref=f"evidence.local.{config.node_identity}",
        require_orchestrator_authorization=False,
    )

    service = NodeApiService(orchestrator, api_config)
    app = create_app(service)
    add_readiness_route(app, service)
    return app


# ---------------------------------------------------------------------------
# Readiness endpoint helper (added to the app in create_hardened_app)
# ---------------------------------------------------------------------------

def add_readiness_route(app: Any, service: NodeApiService) -> None:
    """Attach ``GET /api/v1/node/readiness`` to an existing FastAPI app.

    The readiness probe does **not** require authentication so that deployment
    health checks (e.g. container orchestrators) can call it without a token.
    It returns 200 when the ledger chain is intact, 503 otherwise.

    We add this as a raw Starlette ``Route`` to bypass FastAPI's response-model
    validation pipeline, which would otherwise intercept ``JSONResponse`` returns
    and trigger the custom ``RequestValidationError`` handler.
    """
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse as StarletteJSONResponse
    from starlette.routing import Route

    async def readiness(request: StarletteRequest) -> StarletteJSONResponse:  # noqa: ARG001
        try:
            health = service.health()
            return StarletteJSONResponse(status_code=200, content=health)
        except Exception as exc:
            return StarletteJSONResponse(
                status_code=503,
                content={"status": "degraded", "reason": str(exc)},
            )

    starlette_route = Route("/api/v1/node/readiness", endpoint=readiness, methods=["GET"])
    app.router.routes.insert(0, starlette_route)



# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    """Start the AirBench Node server.

    Usage::

        python -m airbench.node.server          # uses env vars
        python -m airbench.node.server config.yaml   # uses YAML config file
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to YAML config file (optional; env vars used otherwise)")
    parser.add_argument("--check-only", action="store_true", help="Run startup checks and exit without binding")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.config:
            cfg = NodeServerConfig.from_yaml(Path(args.config))
        else:
            cfg = NodeServerConfig.from_env()
    except (EnvironmentError, ValueError) as exc:
        logger.error("Configuration error: %s", exc)
        return 2

    checks = run_startup_checks(cfg)
    for check in checks.checks:
        level = logging.INFO if check["status"] == "ok" else logging.ERROR
        logger.log(level, "Startup check %s: %s — %s", check["name"], check["status"], check.get("detail", ""))

    if not checks.passed:
        logger.error("Startup checks failed; node will not bind.")
        return 1

    if args.check_only:
        logger.info("--check-only: startup checks passed, not binding.")
        return 0

    try:
        import uvicorn  # type: ignore[import-untyped]
    except ImportError:
        logger.error("uvicorn is not installed. Install it with: pip install uvicorn")
        return 1

    try:
        app = build_node_app(cfg, skip_startup_check=True)  # checks already run above
    except RuntimeError as exc:
        logger.error("Failed to build node app: %s", exc)
        return 1

    logger.info(
        "Starting AirBench Node %s on %s:%d (protocol %s)",
        cfg.node_identity, cfg.host, cfg.port, NODE_PROTOCOL_VERSION,
    )
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level=args.log_level.lower())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
