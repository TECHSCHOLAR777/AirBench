"""NVIDIA NIM backend adapter for AirBench.

Implements the same :class:`~contracts.backend.BackendAdapter` protocol as
:class:`~contracts.adapters.vllm_adapter.VllmAdapter` but targets NVIDIA's
NIM (NVIDIA Inference Microservice) OpenAI-compatible endpoint.

NIM differences from vLLM
--------------------------
* **Health path**: NIM uses ``GET /v1/health/ready`` rather than ``GET /health``.
* **Credential policy**: NIM may require an ``Authorization`` header.
  AirBench permits only a ``"local"`` or absent API key; any value that
  looks like a real Bearer token is rejected immediately with
  ``BackendCallError(unavailable)`` so no external credential is sent.
* **Readiness**: same ``GET /v1/models`` path as vLLM.

Everything else — payload construction, tool parsing, structured output,
vision encoding, streaming, cancellation, no-egress enforcement, ledger
events — is identical to the vLLM adapter and is re-used via composition.

Air-gapped safety
-----------------
NIM is included *only* where the target model and runtime officially support
offline startup.  This adapter enforces the same ``HF_HUB_OFFLINE`` /
``TRANSFORMERS_OFFLINE`` env-var check as the vLLM adapter.  It additionally
refuses to send any non-local API key, preventing accidental egress to
NVIDIA's cloud.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterator
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from ..model.backend import (
    BackendCallError,
    BackendCapabilities,
    BackendChunk,
    BackendErrorCode,
    BackendFailure,
    BackendHealth,
    BackendReadiness,
    BackendRequest,
    BackendResponse,
    CancellationToken,
)
from ..provenance.ledger import LedgerStore
from .tool_parsers import BaseToolParser, ToolCallParserRegistry
from .vllm_adapter import VllmAdapter


# ---------------------------------------------------------------------------
# NIM-specific local-credential guard
# ---------------------------------------------------------------------------

_LOCAL_KEYS: frozenset[str] = frozenset({"", "local", "none", "placeholder"})


def _assert_local_key(api_key: str | None, request: BackendRequest) -> None:
    """Raise if *api_key* looks like a real remote credential."""
    key = (api_key or "").strip().lower()
    if key not in _LOCAL_KEYS:
        raise BackendCallError(
            BackendFailure(
                code=BackendErrorCode.unavailable,
                message=(
                    "NIM adapter refuses to send a non-local API key; "
                    "AirBench is air-gapped and must not call NVIDIA cloud endpoints"
                ),
                retryable=False,
                request_id=request.model_call.request_id,
                target_id=request.target_id,
            )
        )


class NimAdapter:
    """OpenAI-compatible adapter for a locally running NVIDIA NIM container.

    Parameters
    ----------
    base_url:
        Root URL of the NIM server, e.g. ``"http://127.0.0.1:8000"``.
    model_name:
        The NIM model identifier, e.g. ``"qwen3-coder-30b-a3b-instruct"``.
    tool_parser:
        Parser for the model family's tool-call format.
    api_key:
        Optional local placeholder key (``"local"`` or ``""``).  Any value
        that resembles a real token causes an immediate ``unavailable`` error.
    ledger:
        Optional :class:`~contracts.ledger.LedgerStore` for lifecycle events.
    capabilities:
        Advertised :class:`~contracts.backend.BackendCapabilities`.
    require_no_egress_env:
        Enforce ``HF_HUB_OFFLINE``/``TRANSFORMERS_OFFLINE`` env vars.
    timeout_s:
        HTTP request timeout in seconds.
    """

    adapter_id = "airbench.nim"
    adapter_version = "1.0"

    def __init__(
        self,
        base_url: str,
        model_name: str,
        *,
        tool_parser: BaseToolParser | None = None,
        api_key: str | None = None,
        ledger: LedgerStore | None = None,
        capabilities: BackendCapabilities | None = None,
        require_no_egress_env: bool = True,
        timeout_s: float = 120.0,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url is required")
        if not model_name.strip():
            raise ValueError("model_name is required")

        # Validate credential before any network activity.
        api_key_norm = (api_key or "").strip().lower()
        if api_key_norm not in _LOCAL_KEYS:
            raise ValueError(
                "NimAdapter only accepts a local placeholder API key ('local', '', or 'none'); "
                "AirBench does not permit real NVIDIA cloud credentials"
            )
        self._api_key = api_key or ""
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._require_no_egress_env = require_no_egress_env
        self._timeout_s = timeout_s

        # Delegate all OpenAI-compatible logic to VllmAdapter.  We override
        # only the health path and credential behaviour.
        self._delegate = VllmAdapter(
            base_url=base_url,
            model_name=model_name,
            tool_parser=tool_parser,
            ledger=ledger,
            capabilities=capabilities,
            require_no_egress_env=require_no_egress_env,
            timeout_s=timeout_s,
        )
        # Expose the same IDs that the delegate uses for ledger events, but
        # override them with our NIM-specific identity so ledger events are
        # correctly attributed.
        self._delegate.adapter_id = self.adapter_id
        self._delegate.adapter_version = self.adapter_version

    # ------------------------------------------------------------------
    # BackendAdapter protocol
    # ------------------------------------------------------------------

    def capabilities(self) -> BackendCapabilities:
        return self._delegate.capabilities()

    def health(self) -> BackendHealth:
        """GET /v1/health/ready — NIM-specific health path."""
        try:
            body = self._get("/v1/health/ready")
            if body is None:
                return BackendHealth.unhealthy
            # NIM returns {"status": "ready"} when healthy.
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    status = data.get("status", "")
                    return BackendHealth.healthy if "ready" in str(status).lower() else BackendHealth.unhealthy
            except json.JSONDecodeError:
                pass
            # A 200 with any body is treated as healthy.
            return BackendHealth.healthy
        except Exception:
            return BackendHealth.unhealthy

    def readiness(self) -> BackendReadiness:
        """GET /v1/models — same as vLLM."""
        return self._delegate.readiness()

    def complete(
        self,
        request: BackendRequest,
        cancellation: CancellationToken | None = None,
    ) -> BackendResponse:
        _assert_local_key(self._api_key, request)
        return self._delegate.complete(request, cancellation)

    def stream(
        self,
        request: BackendRequest,
        cancellation: CancellationToken | None = None,
    ) -> Iterator[BackendChunk]:
        _assert_local_key(self._api_key, request)
        yield from self._delegate.stream(request, cancellation)

    # ------------------------------------------------------------------
    # Internal HTTP (NIM-specific paths)
    # ------------------------------------------------------------------

    def _get(self, path: str) -> bytes | None:
        url = self._base_url + path
        try:
            req = Request(url, method="GET")
            if self._api_key and self._api_key.lower() not in ("", "local", "none"):
                req.add_header("Authorization", f"Bearer {self._api_key}")
            with urlopen(req, timeout=self._timeout_s) as resp:
                return resp.read()
        except HTTPError as exc:
            return None if exc.code and exc.code < 500 else None
        except (URLError, OSError):
            return None


__all__ = ["NimAdapter"]
