from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contracts import (
    BackendHealth,
    BackendReadiness,
    LocalEndpointBinding,
    ModelRegistry,
    ModelRouter,
    VllmAdapter,
)

logger = logging.getLogger(__name__)

_ENABLED_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class LocalEndpointSpec:
    endpoint_id: str
    target_id: str
    base_url: str
    served_model_name: str
    adapter_id: str = 'airbench.vllm'
    adapter_version: str = '0.5'

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

    @classmethod
    def from_env(cls) -> 'ModelServingConfig':
        policy_hash = os.environ.get('AIRBENCH_POLICY_VERSION_HASH', '').strip()
        if not policy_hash:
            raise EnvironmentError('AIRBENCH_POLICY_VERSION_HASH is required')
        e2b_url = os.environ.get('AIRBENCH_MODEL_E2B_URL', 'http://127.0.0.1:18001').strip()
        twelve_url = os.environ.get('AIRBENCH_MODEL_12B_URL', 'http://127.0.0.1:18002').strip()
        e2b_target = os.environ.get('AIRBENCH_MODEL_E2B_TARGET_ID', 'airbench-gemma-4-e2b').strip()
        twelve_target = os.environ.get('AIRBENCH_MODEL_12B_TARGET_ID', 'airbench-gemma-4-12b').strip()
        e2b_served = os.environ.get('AIRBENCH_MODEL_E2B_SERVED_NAME', 'airbench-gemma-4-e2b').strip()
        twelve_served = os.environ.get('AIRBENCH_MODEL_12B_SERVED_NAME', 'airbench-gemma-4-12b').strip()
        try:
            timeout_s = float(os.environ.get('AIRBENCH_MODEL_TIMEOUT_S', '120').strip())
        except ValueError as exc:
            raise EnvironmentError('AIRBENCH_MODEL_TIMEOUT_S must be a number') from exc
        endpoints = (
            LocalEndpointSpec(endpoint_id='ep.e2b.local', target_id=e2b_target,
                              base_url=e2b_url, served_model_name=e2b_served),
            LocalEndpointSpec(endpoint_id='ep.12b.local', target_id=twelve_target,
                              base_url=twelve_url, served_model_name=twelve_served),
        )
        return cls(policy_version_hash=policy_hash, endpoints=endpoints, timeout_s=timeout_s)

    @classmethod
    def single_endpoint(cls, *, policy_version_hash: str,
                        base_url: str = 'http://127.0.0.1:18001',
                        target_id: str = 'airbench-gemma-4-e2b',
                        served_model_name: str = 'airbench-gemma-4-e2b',
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
    for spec in config.endpoints:
        try:
            spec.validate()
        except Exception as exc:
            raise ValueError(f'Endpoint spec for {spec.target_id!r} failed validation: {exc}') from exc
        adapter = VllmAdapter(
            base_url=spec.base_url, model_name=spec.served_model_name,
            endpoint_id=spec.endpoint_id, ledger=ledger,
            require_no_egress_env=config.require_no_egress_env,
            timeout_s=config.timeout_s,
        )
        endpoint_bindings[spec.target_id] = adapter
        logger.info('Registered endpoint binding: target=%s endpoint=%s url=%s',
                    spec.target_id, spec.endpoint_id, spec.base_url)
    router = ModelRouter(
        registry=registry, adapters={},
        policy_version_hash=config.policy_version_hash,
        resource_admission=resource_admission,
        endpoint_bindings=endpoint_bindings,
    )
    logger.info('ModelRouter built: %d endpoint binding(s), policy_hash=%s',
                len(endpoint_bindings), config.policy_version_hash)
    return router


@dataclass(frozen=True, slots=True)
class ModelServingRuntime:
    """A signed registry and the router bound to its endpoint deployments."""

    registry: ModelRegistry
    router: ModelRouter


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
                               artifact_root: str | Path, signing_key: bytes,
                               ledger: Any = None, resource_admission: Any = None) -> ModelServingRuntime:
    """Load the signed roster and build the endpoint-bound router.

    Raises ``RegistryError`` if the roster is unsigned, stale, or its artifacts
    do not hash to the declared digests.  Failing loudly here is deliberate:
    the Node must never start with an unverifiable model roster.
    """
    registry = ModelRegistry.load_roster_file(
        Path(roster_path), signing_key=signing_key, artifact_root=Path(artifact_root),
    )
    router = build_model_router(config, registry, ledger=ledger, resource_admission=resource_admission)
    return ModelServingRuntime(registry=registry, router=router)


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
    if not artifact_root:
        raise EnvironmentError('AIRBENCH_MODEL_STORE is required when model serving is enabled')
    roster_path = os.environ.get('AIRBENCH_MODEL_ROSTER_PATH', 'models/roster/v0/model_roster.yaml').strip()
    signing_key = Path(signing_key_path).read_bytes()
    config = ModelServingConfig.from_env()
    return load_model_serving_runtime(
        config, roster_path=roster_path, artifact_root=artifact_root,
        signing_key=signing_key, ledger=ledger,
        resource_admission=resource_admission or declared_limit_admission,
    )


def probe_endpoint_readiness(router: ModelRouter) -> list[dict[str, Any]]:
    """Report per-endpoint health/readiness without exposing prompts or secrets."""
    results: list[dict[str, Any]] = []
    for target_id, adapter in sorted(router.endpoint_bindings.items()):
        identity: dict[str, Any] = {
            'target_id': target_id,
            'endpoint_id': getattr(adapter, 'endpoint_id', None),
            'adapter_id': getattr(adapter, 'adapter_id', ''),
            'adapter_version': getattr(adapter, 'adapter_version', ''),
        }
        try:
            identity['health'] = adapter.health().value
            identity['readiness'] = adapter.readiness().value
        except Exception:  # never leak provider detail from a probe
            identity['health'] = BackendHealth.unhealthy.value
            identity['readiness'] = BackendReadiness.not_ready.value
        results.append(identity)
    return results


def model_serving_is_ready(router: ModelRouter) -> bool:
    probes = probe_endpoint_readiness(router)
    return bool(probes) and all(
        probe['health'] == BackendHealth.healthy.value and probe['readiness'] == BackendReadiness.ready.value
        for probe in probes
    )


__all__ = [
    'LocalEndpointSpec', 'ModelServingConfig', 'ModelServingRuntime', 'build_model_router',
    'declared_limit_admission', 'load_model_serving_runtime', 'load_model_serving_runtime_from_env',
    'model_serving_enabled', 'model_serving_is_ready', 'probe_endpoint_readiness',
]
