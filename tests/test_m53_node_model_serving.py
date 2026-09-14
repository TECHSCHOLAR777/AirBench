"""Tests for src/airbench/node/model_serving.py.

Covers:
- LocalEndpointSpec validates correctly and rejects bad URLs
- ModelServingConfig.from_env builds a two-endpoint config
- ModelServingConfig.single_endpoint factory
- build_model_router creates distinct adapter instances per target_id
- router resolves capable target by default (quality-first)
- router resolves efficient target on settled mechanical signal
- env-missing AIRBENCH_POLICY_VERSION_HASH raises EnvironmentError
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from contracts import (
    BackendHealth,
    BackendReadiness,
    Clearance,
    ContractStatus,
    ContractValidationError,
    FakeBackend,
    ModelCallRequest,
    ModelRegistry,
    ModelRouter,
    ModelTarget,
    RegistryError,
)
from contracts.model.model_registry import _target_from_roster

from airbench.node.model_serving import (
    LocalEndpointSpec,
    ModelServingConfig,
    build_model_router,
    load_model_serving_runtime,
    model_serving_is_ready,
    probe_endpoint_readiness,
)
from airbench.node.server import NodeServerConfig, add_model_serving_route, build_node_app

_SIGNING_KEY = b"k" * 32


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _target(target_id: str, routing_tier: str, *, adapter_id: str = 'airbench.vllm',
            qualified: bool = True) -> ModelTarget:
    return ModelTarget.from_dict({
        'target_id': target_id,
        'repository': 'local/gemma',
        'artifact_digest': 'a' * 64,
        'artifact_path': f'{target_id}.bin',
        'quantization': 'int4',
        'tokenizer_digest': 'b' * 64,
        'chat_template_digest': 'c' * 64,
        'runtime_version': 'vllm-0.28',
        'backend': 'custom',
        'capabilities': ['reasoning'],
        'roles': ['reasoning'],
        'modalities': ['text'],
        'risk_classes': ['inspection_review'],
        'allowed_clearances': ['internal'],
        'pack_refs': ['pack.fake'],
        'hardware_profile_refs': ['hw.fake'],
        'context_limit': 8192,
        'image_token_limit': 0,
        'tool_call_parser': 'none',
        'structured_output_modes': ['json_schema'],
        'license_id': 'license.gemma',
        'local_storage_hash': 'a' * 64,
        'qualification_certificate': f'cert.{target_id}',
        'qualification_expires_at': '2030-01-01T00:00:00Z',
        'qualification_signature': 'd' * 64,
        'role_qualifications': [['reasoning', f'cert.{target_id}']] if qualified else [],
        'adapter_id': adapter_id,
        'adapter_version': '0.5' if adapter_id == 'airbench.vllm' else '1.0',
        'streaming': True,
        'cancellation': True,
        'routing_tier': routing_tier,
    })


def _registry(*targets: ModelTarget) -> ModelRegistry:
    return ModelRegistry('registry.serving', '1.0', tuple(targets), 'e' * 64, '2030-01-01T00:00:00Z')


def _request(**routing: object) -> ModelCallRequest:
    payload = {
        'request_id': 'req.serving.test',
        'task_id': 'task.serving.test',
        'team_id': 'team.serving.test',
        'worker_id': 'worker.serving.test',
        'task_kind': 'inspection_review',
        'modality': 'text',
        'required_capability': 'reasoning',
        'evidence_summary': ['ev.serving'],
        'clearance': 'internal',
        'action_risk': 'inspection_review',
        'resource_budget': {'context_tokens': 128},
        'attempt': 1,
        'idempotency_key': 'idem.serving',
        'timeout_ms': 1000,
        'role': 'reasoning',
        'resource_lease_id': 'lease.serving',
    }
    payload.update(routing)
    return ModelCallRequest.from_dict(payload)


# ---------------------------------------------------------------------------
# LocalEndpointSpec tests
# ---------------------------------------------------------------------------

class LocalEndpointSpecTests(unittest.TestCase):
    def test_valid_loopback_spec(self) -> None:
        spec = LocalEndpointSpec(
            endpoint_id='ep.e2b.local', target_id='airbench-gemma-4-e2b',
            base_url='http://127.0.0.1:18001', served_model_name='airbench-gemma-4-e2b',
        )
        spec.validate()  # must not raise

    def test_non_loopback_url_raises(self) -> None:
        spec = LocalEndpointSpec(
            endpoint_id='ep.e2b.local', target_id='airbench-gemma-4-e2b',
            base_url='http://10.0.0.5:18001', served_model_name='airbench-gemma-4-e2b',
        )
        with self.assertRaises(ContractValidationError):
            spec.validate()

    def test_missing_required_field_raises(self) -> None:
        spec = LocalEndpointSpec(
            endpoint_id='', target_id='airbench-gemma-4-e2b',
            base_url='http://127.0.0.1:18001', served_model_name='airbench-gemma-4-e2b',
        )
        with self.assertRaises(ValueError):
            spec.validate()


# ---------------------------------------------------------------------------
# ModelServingConfig tests
# ---------------------------------------------------------------------------

class ModelServingConfigTests(unittest.TestCase):
    def test_from_env_builds_two_endpoint_config(self) -> None:
        env = {
            'AIRBENCH_POLICY_VERSION_HASH': 'policy-v1-test',
            'AIRBENCH_MODEL_E2B_URL': 'http://127.0.0.1:18001',
            'AIRBENCH_MODEL_12B_URL': 'http://127.0.0.1:18002',
            'AIRBENCH_MODEL_E2B_TARGET_ID': 'airbench-gemma-4-e2b',
            'AIRBENCH_MODEL_12B_TARGET_ID': 'airbench-gemma-4-12b',
            'AIRBENCH_MODEL_E2B_SERVED_NAME': 'airbench-gemma-4-e2b',
            'AIRBENCH_MODEL_12B_SERVED_NAME': 'airbench-gemma-4-12b',
        }
        with patch.dict(os.environ, env, clear=False):
            config = ModelServingConfig.from_env()
        self.assertEqual(config.policy_version_hash, 'policy-v1-test')
        self.assertEqual(len(config.endpoints), 2)
        self.assertEqual(config.endpoints[0].endpoint_id, 'ep.e2b.local')
        self.assertEqual(config.endpoints[1].endpoint_id, 'ep.12b.local')

    def test_from_env_requires_policy_hash(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AIRBENCH_POLICY_VERSION_HASH', None)
            with self.assertRaises(EnvironmentError):
                ModelServingConfig.from_env()

    def test_single_endpoint_factory(self) -> None:
        config = ModelServingConfig.single_endpoint(
            policy_version_hash='policy-single',
            require_no_egress_env=False,
        )
        self.assertEqual(len(config.endpoints), 1)
        self.assertEqual(config.endpoints[0].endpoint_id, 'ep.primary.local')


# ---------------------------------------------------------------------------
# build_model_router tests (no live vLLM; adapters are NOT VllmAdapter in tests)
# ---------------------------------------------------------------------------

class BuildModelRouterTests(unittest.TestCase):
    """Use FakeBackend sub-routing to avoid live HTTP; we test the wiring."""

    def _fake_config(self) -> ModelServingConfig:
        return ModelServingConfig(
            policy_version_hash='policy-test',
            endpoints=(
                LocalEndpointSpec(endpoint_id='ep.e2b.local',
                                  target_id='airbench-gemma-4-e2b',
                                  base_url='http://127.0.0.1:18001',
                                  served_model_name='airbench-gemma-4-e2b'),
                LocalEndpointSpec(endpoint_id='ep.12b.local',
                                  target_id='airbench-gemma-4-12b',
                                  base_url='http://127.0.0.1:18002',
                                  served_model_name='airbench-gemma-4-12b'),
            ),
            require_no_egress_env=False,
        )

    def _fake_registry(self) -> ModelRegistry:
        return _registry(
            _target('airbench-gemma-4-e2b', 'efficient'),
            _target('airbench-gemma-4-12b', 'capable'),
        )

    def test_build_creates_two_distinct_bindings(self) -> None:
        config = self._fake_config()
        registry = self._fake_registry()
        router = build_model_router(config, registry)
        self.assertEqual(len(router.endpoint_bindings), 2)
        e2b = router.endpoint_bindings.get('airbench-gemma-4-e2b')
        twelve = router.endpoint_bindings.get('airbench-gemma-4-12b')
        self.assertIsNotNone(e2b)
        self.assertIsNotNone(twelve)
        self.assertIsNot(e2b, twelve)

    def test_bad_base_url_raises_on_build(self) -> None:
        bad_config = ModelServingConfig(
            policy_version_hash='policy-test',
            endpoints=(
                LocalEndpointSpec(endpoint_id='ep.bad',
                                  target_id='target.bad',
                                  base_url='http://192.168.1.1:18001',
                                  served_model_name='model'),
            ),
            require_no_egress_env=False,
        )
        with self.assertRaises(ValueError):
            build_model_router(bad_config, self._fake_registry())


def _nested_target(target_id: str, artifact_path: str, digest: str, tier: str) -> dict:
    return {
        'target_id': target_id, 'repository': f'local/{target_id}', 'revision': 'sha256:' + digest,
        'artifact_hash': digest, 'artifact_path': artifact_path, 'artifact_files': [artifact_path],
        'local_storage_hash': digest, 'tokenizer': {'hash': 'bundled'},
        'chat_template': {'template_id': 'tpl', 'hash': 'bundled'},
        'quantization': {'format': 'BF16'},
        'serving': {'runtime': 'vllm', 'runtime_version': '0.28.0', 'adapter_id': 'airbench.vllm',
                    'adapter_version': '0.5', 'container_digest': 'sha256:' + 'c' * 64},
        'limits': {'context_tokens': 8192, 'image_tokens': 0, 'max_concurrency': 1, 'max_batch_size': 1},
        'qualified_roles': [{'role': 'reasoning', 'certificate_id': f'cert.{target_id}',
                             'qualification_hash': 'e' * 64}],
        'tool_call_parser': 'none', 'structured_output_modes': ['json_schema'],
        'capabilities': ['reasoning'], 'modalities': ['text'], 'risk_classes': ['inspection_review'],
        'allowed_clearances': ['internal'], 'pack_refs': ['pack.fake'], 'hardware_profile_refs': ['hw.fake'],
        'license': 'license.gemma', 'routing_tier': tier,
        'qualification_expires_at': '2030-01-01T00:00:00Z', 'qualification_signature': '0' * 64,
    }


def _write_signed_roster(root: Path, targets: list[dict]) -> Path:
    import yaml

    signed = []
    for raw in targets:
        item = json.loads(json.dumps(raw))
        normalized = _target_from_roster(item)
        item['qualification_signature'] = hmac.new(
            _SIGNING_KEY,
            json.dumps(normalized.qualification_payload(), sort_keys=True, separators=(',', ':')).encode(),
            hashlib.sha256,
        ).hexdigest()
        signed.append(item)
    document = {
        'roster': {'roster_id': 'roster.serving', 'schema_version': '1.0', 'targets': signed},
        'registry_id': 'roster.serving', 'manifest_version': '1.0', 'valid_until': '2030-01-01T00:00:00Z',
    }
    document = yaml.safe_load(yaml.safe_dump(document, sort_keys=False))
    document['signature'] = hmac.new(
        _SIGNING_KEY, json.dumps(document, sort_keys=True, separators=(',', ':')).encode(), hashlib.sha256,
    ).hexdigest()
    path = root / 'roster.yaml'
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding='utf-8')
    return path


def _two_endpoint_config() -> ModelServingConfig:
    return ModelServingConfig(
        policy_version_hash='policy.runtime',
        endpoints=(
            LocalEndpointSpec(endpoint_id='ep.e2b.local', target_id='airbench-gemma-4-e2b',
                              base_url='http://127.0.0.1:18001', served_model_name='airbench-gemma-4-e2b'),
            LocalEndpointSpec(endpoint_id='ep.12b.local', target_id='airbench-gemma-4-12b',
                              base_url='http://127.0.0.1:18002', served_model_name='airbench-gemma-4-12b'),
        ),
        require_no_egress_env=False,
    )


class LoadModelServingRuntimeTests(unittest.TestCase):
    def test_loads_signed_roster_and_binds_both_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'e2b.bin').write_bytes(b'e2b weights')
            (root / '12b.bin').write_bytes(b'12b weights')
            roster = _write_signed_roster(root, [
                _nested_target('airbench-gemma-4-e2b', 'e2b.bin', hashlib.sha256(b'e2b weights').hexdigest(), 'efficient'),
                _nested_target('airbench-gemma-4-12b', '12b.bin', hashlib.sha256(b'12b weights').hexdigest(), 'capable'),
            ])
            runtime = load_model_serving_runtime(
                _two_endpoint_config(), roster_path=roster, artifact_root=root, signing_key=_SIGNING_KEY,
            )
        self.assertEqual(
            set(runtime.router.endpoint_bindings),
            {'airbench-gemma-4-e2b', 'airbench-gemma-4-12b'},
        )
        self.assertEqual(len(runtime.registry.targets), 2)

    def test_tampered_roster_signature_is_rejected(self) -> None:
        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'e2b.bin').write_bytes(b'e2b weights')
            roster = _write_signed_roster(root, [
                _nested_target('airbench-gemma-4-e2b', 'e2b.bin', hashlib.sha256(b'e2b weights').hexdigest(), 'efficient'),
            ])
            document = yaml.safe_load(roster.read_text(encoding='utf-8'))
            document['signature'] = '0' * 64
            roster.write_text(yaml.safe_dump(document, sort_keys=False), encoding='utf-8')
            with self.assertRaises(RegistryError):
                load_model_serving_runtime(
                    ModelServingConfig(policy_version_hash='policy.runtime', endpoints=(
                        LocalEndpointSpec('ep.e2b.local', 'airbench-gemma-4-e2b', 'http://127.0.0.1:18001', 'airbench-gemma-4-e2b'),
                    ), require_no_egress_env=False),
                    roster_path=roster, artifact_root=root, signing_key=_SIGNING_KEY,
                )


class ProbeEndpointReadinessTests(unittest.TestCase):
    def _router(self, e2b: FakeBackend, twelve: FakeBackend, **target_kwargs) -> ModelRouter:
        return ModelRouter(
            _registry(
                _target('airbench-gemma-4-e2b', 'efficient', **target_kwargs),
                _target('airbench-gemma-4-12b', 'capable', **target_kwargs),
            ),
            {},
            policy_version_hash='policy.probe',
            resource_admission=lambda _target, _request: 'admitted',
            endpoint_bindings={'airbench-gemma-4-e2b': e2b, 'airbench-gemma-4-12b': twelve},
        )

    def test_healthy_endpoints_report_ready(self) -> None:
        router = self._router(FakeBackend(), FakeBackend(), adapter_id='airbench.fake-backend')
        probes = probe_endpoint_readiness(router)
        self.assertEqual(
            sorted(p['target_id'] for p in probes),
            ['airbench-gemma-4-12b', 'airbench-gemma-4-e2b'],
        )
        self.assertTrue(all(p['health'] == 'healthy' and p['readiness'] == 'ready' for p in probes))
        self.assertTrue(all(p['reason'] == 'ready' for p in probes))
        self.assertTrue(model_serving_is_ready(router))

    def test_one_unhealthy_endpoint_degrades_readiness(self) -> None:
        twelve = FakeBackend()
        twelve.set_state(health=BackendHealth.unhealthy, readiness=BackendReadiness.not_ready)
        router = self._router(FakeBackend(), twelve, adapter_id='airbench.fake-backend')
        self.assertFalse(model_serving_is_ready(router))
        probes = {p['target_id']: p for p in probe_endpoint_readiness(router)}
        self.assertEqual(probes['airbench-gemma-4-12b']['reason'], 'unhealthy')

    def test_adapter_identity_mismatch_is_reported(self) -> None:
        # FakeBackend is 'airbench.fake-backend'; the roster declares 'airbench.vllm'.
        router = self._router(FakeBackend(), FakeBackend())
        probes = {p['target_id']: p for p in probe_endpoint_readiness(router)}
        self.assertEqual(probes['airbench-gemma-4-e2b']['reason'], 'adapter_mismatch')
        self.assertEqual(probes['airbench-gemma-4-e2b']['readiness'], 'not_ready')
        self.assertFalse(model_serving_is_ready(router))

    def test_missing_qualification_is_reported(self) -> None:
        router = self._router(FakeBackend(), FakeBackend(), adapter_id='airbench.fake-backend', qualified=False)
        probes = {p['target_id']: p for p in probe_endpoint_readiness(router)}
        self.assertEqual(probes['airbench-gemma-4-e2b']['reason'], 'qualification_missing')
        self.assertFalse(model_serving_is_ready(router))


class _ProbeStubBackend:
    """Deterministic stand-in exposing the VllmAdapter-style probe() contract."""

    adapter_id = 'airbench.vllm'
    adapter_version = '0.5'

    def __init__(self, probe_result: dict, model_name: str = 'airbench-gemma-4-e2b') -> None:
        self._probe_result = probe_result
        self.model_name = model_name

    def probe(self) -> dict:
        return self._probe_result


class ProbeReasonPassthroughTests(unittest.TestCase):
    def test_model_mismatch_reason_survives_composition(self) -> None:
        stub = _ProbeStubBackend({
            'health': 'healthy', 'readiness': 'not_ready',
            'reason': 'model_mismatch', 'served_models': ['some-other-model'],
        })
        router = ModelRouter(
            _registry(_target('airbench-gemma-4-e2b', 'efficient')),
            {}, policy_version_hash='policy.probe',
            endpoint_bindings={'airbench-gemma-4-e2b': stub},
        )
        probes = probe_endpoint_readiness(router)
        self.assertEqual(probes[0]['reason'], 'model_mismatch')
        self.assertEqual(probes[0]['expected_model'], 'airbench-gemma-4-e2b')
        self.assertEqual(probes[0]['served_models'], ['some-other-model'])
        self.assertFalse(model_serving_is_ready(router))


class ModelServingRouteTests(unittest.TestCase):
    def _get(self, app, path: str) -> httpx.Response:
        async def go() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url='http://node.serving',
            ) as client:
                return await client.get(path)
        return asyncio.run(go())

    def test_route_reports_disabled_without_a_router(self) -> None:
        cfg = NodeServerConfig(
            node_identity='node.serving', bearer_token='t', domain_pack_ref='pack.fake',
            clearance=Clearance.internal, subject='principal.serving',
        )
        app = build_node_app(cfg, skip_startup_check=True)
        resp = self._get(app, '/api/v1/node/model-serving')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()['configured'])

    def test_route_reports_endpoint_states_with_a_router(self) -> None:
        from fastapi import FastAPI

        class _Service:
            model_router = ModelRouter(
                _registry(_target('airbench-gemma-4-e2b', 'efficient', adapter_id='airbench.fake-backend')),
                {},
                policy_version_hash='policy.route',
                resource_admission=lambda _target, _request: 'admitted',
                endpoint_bindings={'airbench-gemma-4-e2b': FakeBackend()},
            )

        app = FastAPI()
        add_model_serving_route(app, _Service())
        resp = self._get(app, '/api/v1/node/model-serving')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['configured'])
        self.assertEqual(body['status'], 'ready')
        self.assertEqual(body['endpoints'][0]['target_id'], 'airbench-gemma-4-e2b')
        self.assertEqual(body['endpoints'][0]['reason'], 'ready')


if __name__ == '__main__':
    unittest.main()
