from __future__ import annotations

import logging
import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contracts import (
    BackendHealth,
    BackendReadiness,
    BackendCapabilities,
    LocalEndpointBinding,
    ModelRegistry,
    ModelRouter,
    VllmAdapter,
    ToolCallParserRegistry,
)
from contracts.model.deployment_attestation import RemoteDeploymentAttestation

logger = logging.getLogger(__name__)

_ENABLED_VALUES = {"1", "true", "yes", "on"}

# Shared, bounded executor for endpoint probes. A per-poll ThreadPoolExecutor
# leaked one thread per endpoint per request when endpoints hung; a bounded
# shared pool caps that cost for the life of the process.
_PROBE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="airbench-probe")


@dataclass(frozen=True, slots=True)
class LocalEndpointSpec:
    endpoint_id: str
    target_id: str
    base_url: str
    served_model_name: str
    adapter_id: str = 'airbench.vllm'
    adapter_version: str = '0.5'

    @classmethod
    def from_dict(cls, value: Any) -> 'LocalEndpointSpec':
        if not isinstance(value, dict):
            raise ValueError('endpoint entries must be objects')
        allowed = {'endpoint_id', 'target_id', 'base_url', 'served_model_name', 'adapter_id', 'adapter_version'}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f'unknown endpoint fields: {sorted(unknown)}')
        spec = cls(**{key: value[key] for key in allowed if key in value})
        spec.validate()
        return spec

    def validate(self) -> None:
        for name in ('endpoint_id', 'target_id', 'base_url', 'served_model_name'):
            value = getattr(self, name)
            if not value or not value.strip():
                raise ValueError(f'LocalEndpointSpec.{name} is required')
        LocalEndpointBinding.from_dict({
            'endpoint_id': self.endpoint_id,
            'target_id': self.target_id,
            'base_url': self.base_url,
            'served_model_name': self.served_model_name,
            'adapter_id': self.adapter_id,
            'adapter_version': self.adapter_version,
        })


@dataclass(frozen=True, slots=True)
class ModelServingConfig:
    policy_version_hash: str
    endpoints: tuple[LocalEndpointSpec, ...] = ()
    require_no_egress_env: bool = True
    timeout_s: float = 120.0
    allow_candidate_qualification: bool = False

    @classmethod
    def from_env(cls) -> 'ModelServingConfig':
        policy_hash = os.environ.get('AIRBENCH_POLICY_VERSION_HASH', '').strip()
        if not policy_hash:
            raise EnvironmentError('AIRBENCH_POLICY_VERSION_HASH is required')
        raw_endpoints = os.environ.get('AIRBENCH_MODEL_ENDPOINTS_JSON', '').strip()
        if not raw_endpoints:
            raise EnvironmentError('AIRBENCH_MODEL_ENDPOINTS_JSON is required')
        try:
            endpoint_items = json.loads(raw_endpoints)
        except json.JSONDecodeError as exc:
            raise EnvironmentError('AIRBENCH_MODEL_ENDPOINTS_JSON must be valid JSON') from exc
        if not isinstance(endpoint_items, list) or not endpoint_items:
            raise EnvironmentError('AIRBENCH_MODEL_ENDPOINTS_JSON must be a non-empty array')
        try:
            endpoints = tuple(LocalEndpointSpec.from_dict(item) for item in endpoint_items)
        except (TypeError, ValueError) as exc:
            raise EnvironmentError(f'invalid model endpoint list: {exc}') from exc
        try:
            timeout_s = float(os.environ.get('AIRBENCH_MODEL_TIMEOUT_S', '120').strip())
        except ValueError as exc:
            raise EnvironmentError('AIRBENCH_MODEL_TIMEOUT_S must be a number') from exc
        allow_candidates = os.environ.get('AIRBENCH_MODEL_ALLOW_CANDIDATE_QUALIFICATION', '').strip().lower() in _ENABLED_VALUES
        return cls(policy_version_hash=policy_hash, endpoints=endpoints, timeout_s=timeout_s,
                   allow_candidate_qualification=allow_candidates)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> 'ModelServingConfig':
        endpoints = tuple(LocalEndpointSpec.from_dict(item) for item in value.get('endpoints', ()))
        return cls(policy_version_hash=str(value.get('policy_version_hash', '')), endpoints=endpoints,
                   require_no_egress_env=bool(value.get('require_no_egress_env', True)),
                   timeout_s=float(value.get('timeout_s', 120.0)),
                   allow_candidate_qualification=bool(value.get('allow_candidate_qualification', False)))

    @classmethod
    def single_endpoint(cls, *, policy_version_hash: str,
                        base_url: str,
                        target_id: str,
                        served_model_name: str,
                        require_no_egress_env: bool = True,
                        timeout_s: float = 120.0) -> 'ModelServingConfig':
        return cls(policy_version_hash=policy_version_hash,
                   endpoints=(LocalEndpointSpec(endpoint_id='ep.primary.local',
                               target_id=target_id, base_url=base_url,
                               served_model_name=served_model_name),),
                   require_no_egress_env=require_no_egress_env, timeout_s=timeout_s)


def build_model_router(config: ModelServingConfig, registry: ModelRegistry, *,
                       ledger: Any = None, resource_admission: Any = None) -> ModelRouter:
    endpoint_bindings: dict[str, VllmAdapter] = {}
    targets = {target.target_id: target for target in registry.targets}
    if len({spec.target_id for spec in config.endpoints}) != len(config.endpoints):
        raise ValueError('model endpoint target IDs must be unique')
    for spec in config.endpoints:
        try:
            spec.validate()
        except Exception as exc:
            raise ValueError(f'Endpoint spec for {spec.target_id!r} failed validation: {exc}') from exc
        target = targets.get(spec.target_id)
        if target is None:
            raise ValueError(f'endpoint target {spec.target_id!r} is absent from the signed roster')
        if spec.adapter_id != target.adapter_id or spec.adapter_version != target.adapter_version:
            raise ValueError(f'endpoint adapter identity does not match signed target {spec.target_id!r}')
        if target.backend != 'vllm':
            raise ValueError(f'endpoint target {spec.target_id!r} is not a vLLM target')
        adapter = VllmAdapter(
            base_url=spec.base_url, model_name=spec.served_model_name,
            endpoint_id=spec.endpoint_id, ledger=ledger,
            require_no_egress_env=config.require_no_egress_env,
            timeout_s=config.timeout_s,
            tool_parser=ToolCallParserRegistry.get(target.tool_call_parser),
            capabilities=BackendCapabilities(
                structured_output_modes=target.structured_output_modes,
                tool_calling=target.tool_call_parser != 'none',
                modalities=target.modalities,
                streaming=target.streaming,
                cancellation=target.cancellation,
                max_context_tokens=target.context_limit,
            ),
            enable_thinking=target.enable_thinking,
            max_images=target.max_images,
            max_videos=target.max_videos,
            max_output_tokens=target.max_output_tokens,
        )
        endpoint_bindings[spec.target_id] = adapter
        logger.info('Registered endpoint binding: target=%s endpoint=%s url=%s',
                    spec.target_id, spec.endpoint_id, spec.base_url)
    router = ModelRouter(
        registry=registry, adapters={},
        policy_version_hash=config.policy_version_hash,
        resource_admission=resource_admission,
        endpoint_bindings=endpoint_bindings,
        allow_candidate_qualification=config.allow_candidate_qualification,
    )
    logger.info('ModelRouter built: %d endpoint binding(s), policy_hash=%s',
                len(endpoint_bindings), config.policy_version_hash)
    return router


@dataclass(frozen=True, slots=True)
class ModelServingRuntime:
    """A signed registry and the router bound to its endpoint deployments."""

    registry: ModelRegistry
    router: ModelRouter
    deployment_attestation: RemoteDeploymentAttestation | None = None


def model_serving_enabled() -> bool:
    return os.environ.get('AIRBENCH_MODEL_SERVING_ENABLED', '').strip().lower() in _ENABLED_VALUES


def declared_limit_admission(target: Any, request: Any) -> str:
    """Deterministic demo admission from the signed target's declared envelope.

    This is intentionally conservative and is **not** a substitute for the M5.2
    measured hardware admission.  Qualification and role/clearance/risk/modality
    eligibility are still enforced by the registry first; this only refuses a
    request whose declared context budget exceeds the target's own signed
    ``context_limit`` (and refuses zero/unknown limits for local targets).
    """
    limit = getattr(target, 'context_limit', 0)
    requested = request.resource_budget.get('context_tokens', 0)
    if not isinstance(limit, int) or limit < 1:
        return 'needs_review'
    if requested > limit:
        return 'rejected'
    return 'admitted'


def load_model_serving_runtime(config: ModelServingConfig, *, roster_path: str | Path,
                               artifact_root: str | Path | None, signing_key: bytes,
                               deployment_attestation_path: str | Path | None = None,
                               attestation_signing_key: bytes | None = None,
                               ledger: Any = None, resource_admission: Any = None) -> ModelServingRuntime:
    """Load the signed roster and build the endpoint-bound router.

    Raises ``RegistryError`` if the roster is unsigned, stale, or its artifacts
    do not hash to the declared digests.  Failing loudly here is deliberate:
    the Node must never start with an unverifiable model roster.
    """
    attestation: RemoteDeploymentAttestation | None = None
    if deployment_attestation_path is not None:
        if not attestation_signing_key:
            raise EnvironmentError('attestation_signing_key is required for remote model serving')
        # No local model root is consulted in this path.  The attestation is
        # the signed proof of the remote artifact inventory and runtime.
        registry = ModelRegistry.load_roster_file(
            Path(roster_path), signing_key=signing_key, artifact_root=Path(roster_path).parent,
            verify_artifacts=False,
        )
        attestation = RemoteDeploymentAttestation.load_file(
            Path(deployment_attestation_path), signing_key=attestation_signing_key,
        )
        attestation.verify_bindings(registry, config.endpoints)
    else:
        if artifact_root is None:
            raise EnvironmentError('artifact_root is required for local model serving')
        registry = ModelRegistry.load_roster_file(
            Path(roster_path), signing_key=signing_key, artifact_root=Path(artifact_root),
        )
    router = build_model_router(config, registry, ledger=ledger, resource_admission=resource_admission)
    return ModelServingRuntime(registry=registry, router=router, deployment_attestation=attestation)


def load_model_serving_runtime_from_env(*, ledger: Any = None,
                                        resource_admission: Any = None) -> ModelServingRuntime | None:
    """Build the runtime from environment variables, or ``None`` when disabled."""
    if not model_serving_enabled():
        return None
    signing_key_path = os.environ.get('AIRBENCH_MODEL_SIGNING_KEY_PATH', '').strip()
    if not signing_key_path:
        raise EnvironmentError('AIRBENCH_MODEL_SIGNING_KEY_PATH is required when model serving is enabled')
    artifact_root = (
        os.environ.get('AIRBENCH_MODEL_STORE', '').strip()
        or os.environ.get('AIRBENCH_MODEL_STORE_ROOT', '').strip()
    )
    roster_path = os.environ.get('AIRBENCH_MODEL_ROSTER_PATH', '').strip()
    if not roster_path:
        raise EnvironmentError('AIRBENCH_MODEL_ROSTER_PATH is required when model serving is enabled')
    signing_key = Path(signing_key_path).read_bytes()
    config = ModelServingConfig.from_env()
    attestation_path = os.environ.get('AIRBENCH_MODEL_DEPLOYMENT_ATTESTATION_PATH', '').strip() or None
    attestation_key_path = os.environ.get('AIRBENCH_MODEL_ATTESTATION_SIGNING_KEY_PATH', '').strip()
    if attestation_path and not attestation_key_path:
        raise EnvironmentError('AIRBENCH_MODEL_ATTESTATION_SIGNING_KEY_PATH is required with a deployment attestation')
    if not attestation_path and not artifact_root:
        raise EnvironmentError('AIRBENCH_MODEL_STORE is required for local model serving')
    return load_model_serving_runtime(
        config, roster_path=roster_path, artifact_root=artifact_root,
        signing_key=signing_key, deployment_attestation_path=attestation_path,
        attestation_signing_key=Path(attestation_key_path).read_bytes() if attestation_key_path else None,
        ledger=ledger,
        resource_admission=resource_admission or declared_limit_admission,
    )


def _probe_adapter(adapter: Any) -> dict[str, Any]:
    """Probe one adapter, preferring its one-pass ``probe()`` when available."""
    probe = getattr(adapter, "probe", None)
    if probe is not None:
        return probe()
    health = adapter.health().value
    readiness = adapter.readiness().value
    if health != BackendHealth.healthy.value:
        reason = "unhealthy"
    elif readiness != BackendReadiness.ready.value:
        reason = "not_ready"
    else:
        reason = "ready"
    return {"health": health, "readiness": readiness, "reason": reason, "served_models": []}


def _endpoint_probe_unavailable() -> dict[str, Any]:
    return {
        "health": BackendHealth.unhealthy.value,
        "readiness": BackendReadiness.not_ready.value,
        "reason": "unhealthy",
        "served_models": [],
    }


def probe_endpoint_readiness(router: ModelRouter, *, timeout_s: float | None = None) -> list[dict[str, Any]]:
    """Report per-endpoint health/readiness with a typed reason.

    The reason is one of ``ready``, ``unhealthy``, ``not_ready``,
    ``model_mismatch``, ``adapter_mismatch``, or ``qualification_missing``.
    Endpoint-level reasons come from the adapter probe; the registry adds the
    signed roster's adapter-identity and qualification checks.  No prompts,
    secrets, or provider error text are ever exposed.
    """
    results: list[dict[str, Any]] = []
    targets = {target.target_id: target for target in getattr(router.registry, "targets", ())}
    for target_id, adapter in sorted(router.endpoint_bindings.items()):
        identity: dict[str, Any] = {
            'target_id': target_id,
            'endpoint_id': getattr(adapter, 'endpoint_id', None),
            'adapter_id': getattr(adapter, 'adapter_id', ''),
            'adapter_version': getattr(adapter, 'adapter_version', ''),
        }
        expected_model = getattr(adapter, 'model_name', None)
        if expected_model:
            identity['expected_model'] = expected_model
        try:
            if timeout_s is None:
                probe = _probe_adapter(adapter)
            else:
                # Provider probes must never make the Node status route wait
                # for the full model-call timeout.  A timed-out probe is a
                # visible degraded state; routing still fails closed.
                future = _PROBE_EXECUTOR.submit(_probe_adapter, adapter)
                try:
                    probe = future.result(timeout=max(0.1, timeout_s))
                except TimeoutError:
                    probe = _endpoint_probe_unavailable()
        except Exception:  # never leak provider detail from a probe
            probe = _endpoint_probe_unavailable()
        identity.update(probe)
        # Registry-level checks composed on a live endpoint: the bound adapter
        # must match the signed target's adapter identity, and the target must
        # carry qualification certificates for its roles.
        target = targets.get(target_id)
        if probe.get('reason') == 'ready' and target is not None:
            if ((target.adapter_id and identity['adapter_id'] != target.adapter_id)
                    or (target.adapter_version and identity['adapter_version'] != target.adapter_version)):
                identity['readiness'] = BackendReadiness.not_ready.value
                identity['reason'] = 'adapter_mismatch'
            elif not target.qualification_certificate or not target.role_qualifications:
                identity['readiness'] = BackendReadiness.not_ready.value
                identity['reason'] = 'qualification_missing'
        results.append(identity)
    return results


def model_serving_is_ready(router: ModelRouter) -> bool:
    probes = probe_endpoint_readiness(router)
    return bool(probes) and all(probe.get('reason') == 'ready' for probe in probes)


__all__ = [
    'LocalEndpointSpec', 'ModelServingConfig', 'ModelServingRuntime', 'build_model_router',
    'declared_limit_admission', 'load_model_serving_runtime', 'load_model_serving_runtime_from_env',
    'model_serving_enabled', 'model_serving_is_ready', 'probe_endpoint_readiness',
]
