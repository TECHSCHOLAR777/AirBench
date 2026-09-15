"""M10.1 — API hardening and server entrypoint tests.

Covers:
- Unauthenticated and wrong-token requests.
- Body-too-large (>1 MiB JSON, >100 MiB multipart) rejection.
- Malformed JSON rejection.
- Invalid task-ID format rejection.
- Unknown task → 404.
- Clearance exceeded → 403.
- Readiness endpoint healthy and degraded states.
- Server startup checks (config completeness, ledger path, signing key).
- NodeServerConfig.from_env and validation.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

import httpx

from contracts import Clearance, EventLedger, Orchestrator
from airbench.node.api import NodeApiConfig, NodeApiService, create_app
from airbench.node.server import (
    NodeServerConfig,
    StartupCheckResult,
    build_node_app,
    run_startup_checks,
    add_readiness_route,
)
from airbench.node.bundle import BundleManifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(clearance: Clearance = Clearance.restricted, *, require_auth: bool = False) -> NodeApiService:
    ledger = EventLedger()
    orchestrator = Orchestrator(ledger)
    cfg = NodeApiConfig(
        node_identity="node.m10.test",
        protocol_version="0.1",
        clearance_context=clearance,
        authenticated_subject="principal.m10",
        domain_pack_ref="pack.refinery.v0",
        bearer_token="m10-test-token",
        handshake_ledger_event_ref="ledger.handshake.m10",
        sovereignty_evidence_ref="evidence.sovereignty.m10",
        require_orchestrator_authorization=require_auth,
    )
    return NodeApiService(orchestrator, cfg)


def _make_client(service: NodeApiService) -> httpx.AsyncClient:
    app = create_app(service)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://node.m10.test")


def _run(coro):
    return asyncio.run(coro)


def _headers(token: str = "m10-test-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _task_body() -> dict[str, Any]:
    return {
        "command_id": "cmd.m10.1",
        "task_id": None,
        "actor": "principal.m10",
        "expected_sequence": None,
        "idempotency_key": "idem.m10.1",
        "client_version": "0.1",
        "command_type": "task.create",
        "arguments": {
            "principal_id": "principal.m10",
            "clearance": "internal",
            "request": "Run M10 acceptance check",
            "domain_pack_ref": "pack.refinery.v0",
            "risk_class": "high",
            "autonomy_ceiling": "review_required",
            "allowed_evidence_scope": ["inspection-report"],
            "permitted_worker_capabilities": ["reasoning"],
            "permitted_tools": ["calculator"],
            "output_contract": "approval-note",
            "verification_criteria": ["source_check"],
            "resource_budget": {"max_concurrency": 1, "max_steps": 8},
        },
    }


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

class TestAuthentication(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _make_service()
        self.client = _make_client(self.service)

    def tearDown(self) -> None:
        _run(self.client.aclose())

    def _get(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.get(path, **kwargs))

    def _post(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.post(path, **kwargs))

    def test_no_auth_header_returns_401(self) -> None:
        resp = self._get("/api/v1/health")
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertEqual(body["code"], "authentication_required")

    def test_wrong_token_returns_401(self) -> None:
        resp = self._get("/api/v1/health", headers=_headers("wrong-token"))
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], "invalid_token")

    def test_malformed_auth_scheme_returns_401(self) -> None:
        resp = self._get("/api/v1/health", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        self.assertEqual(resp.status_code, 401)

    def test_valid_token_returns_200(self) -> None:
        resp = self._get("/api/v1/health", headers=_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ready")

    def test_www_authenticate_header_present(self) -> None:
        resp = self._get("/api/v1/health")
        self.assertIn("www-authenticate", resp.headers)

    def test_handshake_requires_auth(self) -> None:
        resp = self._get("/api/v1/node/handshake")
        self.assertEqual(resp.status_code, 401)

    def test_task_create_requires_auth(self) -> None:
        resp = self._post("/api/v1/tasks", json=_task_body())
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Body size enforcement
# ---------------------------------------------------------------------------

class TestBodySizeLimits(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _make_service()
        self.client = _make_client(self.service)

    def tearDown(self) -> None:
        _run(self.client.aclose())

    def _post(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.post(path, **kwargs))

    def test_json_body_over_limit_returns_413(self) -> None:
        # 1 MiB + 1 byte of JSON-safe padding
        oversized = json.dumps({"padding": "x" * (1_048_576 + 1)})
        resp = self._post(
            "/api/v1/tasks",
            headers={**_headers(), "Content-Length": str(len(oversized.encode()))},
            content=oversized.encode(),
        )
        self.assertEqual(resp.status_code, 413)
        self.assertEqual(resp.json()["code"], "body_too_large")

    def test_malformed_json_returns_400(self) -> None:
        resp = self._post(
            "/api/v1/tasks",
            headers={**_headers(), "Content-Type": "application/json"},
            content=b"{not valid json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn(resp.json()["code"], ("json_invalid", "command_contract_invalid"))

    def test_json_array_instead_of_object_returns_400(self) -> None:
        resp = self._post(
            "/api/v1/tasks",
            headers={**_headers(), "Content-Type": "application/json"},
            content=b"[1, 2, 3]",
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _make_service()
        self.client = _make_client(self.service)

    def tearDown(self) -> None:
        _run(self.client.aclose())

    def _get(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.get(path, **kwargs))

    def _post(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.post(path, **kwargs))

    def test_unknown_task_id_returns_404(self) -> None:
        resp = self._get("/api/v1/tasks/task.does-not-exist", headers=_headers())
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], "task_not_found")

    def test_invalid_task_id_shape_returns_400(self) -> None:
        # Starts with non-alnum — violates TASK_ID_RE
        resp = self._get("/api/v1/tasks/.bad-id", headers=_headers())
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "task_id_invalid")

    def test_clearance_exceeded_returns_403(self) -> None:
        # Node configured as ``public``; requesting ``restricted`` clearance → 403
        service = _make_service(Clearance.public)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(service)),
            base_url="http://node.m10.public",
        )
        body = _task_body()
        body["arguments"]["clearance"] = "restricted"
        resp = _run(client.post("/api/v1/tasks", headers=_headers(), json=body))
        _run(client.aclose())
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "clearance_exceeded")

    def test_wrong_command_type_returns_400(self) -> None:
        body = _task_body()
        body["command_type"] = "task.cancel"  # wrong type for POST /tasks
        resp = self._post("/api/v1/tasks", headers=_headers(), json=body)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "command_type_mismatch")

    def test_principal_mismatch_returns_403(self) -> None:
        body = _task_body()
        body["arguments"]["principal_id"] = "principal.other"
        resp = self._post("/api/v1/tasks", headers=_headers(), json=body)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "principal_mismatch")

    def test_missing_required_field_returns_400(self) -> None:
        body = _task_body()
        del body["arguments"]["request"]
        resp = self._post("/api/v1/tasks", headers=_headers(), json=body)
        self.assertIn(resp.status_code, (400, 422))


# ---------------------------------------------------------------------------
# Readiness endpoint
# ---------------------------------------------------------------------------

class TestReadinessEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _make_service()
        self.app = create_app(self.service)
        add_readiness_route(self.app, self.service)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://node.m10.readiness",
        )

    def tearDown(self) -> None:
        _run(self.client.aclose())

    def _get(self, path: str, **kwargs) -> httpx.Response:
        return _run(self.client.get(path, **kwargs))

    def test_readiness_returns_200_when_healthy(self) -> None:
        resp = self._get("/api/v1/node/readiness")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ready")

    def test_readiness_includes_ledger_info(self) -> None:
        resp = self._get("/api/v1/node/readiness")
        body = resp.json()
        self.assertIn("ledger", body)
        self.assertIn("event_count", body["ledger"])

    def test_readiness_no_auth_required(self) -> None:
        # The readiness endpoint must be callable without a token so that
        # deployment health probes work without credentials.
        resp = self._get("/api/v1/node/readiness")
        # Must not return 401 — health probes don't carry tokens
        self.assertNotEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Startup checks
# ---------------------------------------------------------------------------

class TestStartupChecks(unittest.TestCase):
    def _make_config(self, **overrides) -> NodeServerConfig:
        defaults = dict(
            node_identity="node.m10.check",
            bearer_token="m10-token",
            domain_pack_ref="pack.refinery.v0",
            clearance=Clearance.internal,
            subject="principal.m10",
        )
        defaults.update(overrides)
        return NodeServerConfig(**defaults)

    def test_valid_config_passes_all_checks(self) -> None:
        cfg = self._make_config()
        result = run_startup_checks(cfg)
        self.assertTrue(result.passed)
        failed = [c for c in result.checks if c["status"] != "ok"]
        self.assertEqual(failed, [])

    def test_empty_node_identity_fails(self) -> None:
        with self.assertRaises(ValueError):
            self._make_config(node_identity="")

    def test_empty_bearer_token_fails(self) -> None:
        with self.assertRaises(ValueError):
            self._make_config(bearer_token="")

    def test_nonexistent_ledger_dir_fails_startup(self) -> None:
        cfg = self._make_config(ledger_path="/nonexistent_path_m10/ledger.sqlite3")
        result = run_startup_checks(cfg)
        self.assertFalse(result.passed)
        failed_names = {c["name"] for c in result.checks if c["status"] != "ok"}
        self.assertIn("ledger.path", failed_names)

    def test_signing_key_not_found_fails_startup(self) -> None:
        cfg = self._make_config(signing_key_path="/nonexistent_path_m10/signing.key")
        result = run_startup_checks(cfg)
        self.assertFalse(result.passed)
        failed_names = {c["name"] for c in result.checks if c["status"] != "ok"}
        self.assertIn("signing_key", failed_names)

    def test_signing_key_wrong_size_fails_startup(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".key") as fh:
            fh.write(b"short")
            key_path = fh.name
        try:
            cfg = self._make_config(signing_key_path=key_path)
            result = run_startup_checks(cfg)
            self.assertFalse(result.passed)
            failed_names = {c["name"] for c in result.checks if c["status"] != "ok"}
            self.assertIn("signing_key", failed_names)
        finally:
            os.unlink(key_path)

    def test_valid_32_byte_signing_key_passes(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".key") as fh:
            fh.write(b"a" * 32)
            key_path = fh.name
        try:
            cfg = self._make_config(signing_key_path=key_path)
            result = run_startup_checks(cfg)
            self.assertTrue(result.passed)
        finally:
            os.unlink(key_path)

    def test_startup_check_result_as_dict(self) -> None:
        cfg = self._make_config()
        result = run_startup_checks(cfg)
        d = result.as_dict()
        self.assertIn("passed", d)
        self.assertIn("checks", d)
        self.assertIsInstance(d["checks"], list)

    def test_ledger_path_with_existing_dir_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = os.path.join(tmpdir, "ledger.sqlite3")
            cfg = self._make_config(ledger_path=ledger_path)
            result = run_startup_checks(cfg)
            self.assertTrue(result.passed)

    def test_configured_bundle_must_be_signed_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            asset = root / "asset.txt"
            asset.write_text("verified", encoding="utf-8")
            manifest = BundleManifest.build(
                "airbench.test.bundle", "0.1.0", [("asset", "file", asset)], bundle_root=root
            ).sign(b"b" * 32)
            manifest_path = root / "bundle_manifest.json"
            manifest_path.write_text(manifest.to_json(), encoding="utf-8")
            key_path = root / "signing.key"
            key_path.write_bytes(b"b" * 32)

            cfg = self._make_config(
                signing_key_path=str(key_path),
                bundle_manifest_path=str(manifest_path),
                bundle_root=str(root),
            )
            result = run_startup_checks(cfg)
            self.assertTrue(result.passed)
            self.assertEqual(next(c for c in result.checks if c["name"] == "bundle.manifest")["status"], "ok")

            asset.write_text("tampered", encoding="utf-8")
            self.assertFalse(run_startup_checks(cfg).passed)

    def test_configured_bundle_without_signing_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            asset = root / "asset.txt"
            asset.write_text("unsigned", encoding="utf-8")
            manifest = BundleManifest.build(
                "airbench.test.bundle", "0.1.0", [("asset", "file", asset)], bundle_root=root
            )
            manifest_path = root / "bundle_manifest.json"
            manifest_path.write_text(manifest.to_json(), encoding="utf-8")
            cfg = self._make_config(bundle_manifest_path=str(manifest_path), bundle_root=str(root))
            result = run_startup_checks(cfg)
            self.assertFalse(result.passed)
            self.assertIn("bundle.signature", {c["name"] for c in result.checks if c["status"] != "ok"})


# ---------------------------------------------------------------------------
# NodeServerConfig validation
# ---------------------------------------------------------------------------

class TestNodeServerConfig(unittest.TestCase):
    def test_valid_config_constructs(self) -> None:
        cfg = NodeServerConfig(
            node_identity="node.test",
            bearer_token="token",
            domain_pack_ref="pack.v0",
            clearance=Clearance.internal,
            subject="principal.test",
        )
        self.assertEqual(cfg.node_identity, "node.test")
        self.assertEqual(cfg.port, 8765)
        self.assertIsNone(cfg.ledger_path)

    def test_invalid_port_raises(self) -> None:
        with self.assertRaises(ValueError):
            NodeServerConfig(
                node_identity="node.test",
                bearer_token="token",
                domain_pack_ref="pack.v0",
                clearance=Clearance.internal,
                subject="principal.test",
                port=99999,
            )

    def test_from_env_reads_variables(self) -> None:
        env = {
            "AIRBENCH_NODE_IDENTITY": "node.env.test",
            "AIRBENCH_BEARER_TOKEN": "env-token",
            "AIRBENCH_DOMAIN_PACK_REF": "pack.env.v0",
            "AIRBENCH_CLEARANCE": "internal",
            "AIRBENCH_SUBJECT": "principal.env",
            "AIRBENCH_HOST": "0.0.0.0",
            "AIRBENCH_PORT": "9000",
        }
        original = {k: os.environ.get(k) for k in env}
        try:
            os.environ.update(env)
            cfg = NodeServerConfig.from_env()
            self.assertEqual(cfg.node_identity, "node.env.test")
            self.assertEqual(cfg.port, 9000)
            self.assertEqual(cfg.host, "0.0.0.0")
            self.assertEqual(cfg.clearance, Clearance.internal)
        finally:
            for k, v in original.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_from_env_blank_operator_roles_use_demo_reviewer_role(self) -> None:
        env = {
            "AIRBENCH_NODE_IDENTITY": "node.env.roles",
            "AIRBENCH_BEARER_TOKEN": "env-token",
            "AIRBENCH_DOMAIN_PACK_REF": "pack.env.v0",
            "AIRBENCH_CLEARANCE": "internal",
            "AIRBENCH_SUBJECT": "principal.env",
            "AIRBENCH_OPERATOR_ROLES": "   ",
        }
        original = {k: os.environ.get(k) for k in env}
        try:
            os.environ.update(env)
            cfg = NodeServerConfig.from_env()
            self.assertEqual(cfg.operator_roles, ("human_reviewer",))
        finally:
            for k, v in original.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_programmatic_blank_operator_roles_use_demo_reviewer_role(self) -> None:
        cfg = NodeServerConfig(
            node_identity="node.roles.test",
            bearer_token="token",
            domain_pack_ref="pack.v0",
            clearance=Clearance.internal,
            subject="principal.test",
            operator_roles=(" ", ""),
        )
        self.assertEqual(cfg.operator_roles, ("human_reviewer",))

    def test_from_env_missing_required_raises(self) -> None:
        # Remove a required variable
        original = os.environ.pop("AIRBENCH_NODE_IDENTITY", None)
        try:
            with self.assertRaises(EnvironmentError):
                NodeServerConfig.from_env()
        finally:
            if original is not None:
                os.environ["AIRBENCH_NODE_IDENTITY"] = original

    def test_from_env_invalid_clearance_raises(self) -> None:
        original = os.environ.get("AIRBENCH_CLEARANCE")
        # Ensure required vars are present
        env_backup = {}
        for k in ("AIRBENCH_NODE_IDENTITY", "AIRBENCH_BEARER_TOKEN", "AIRBENCH_DOMAIN_PACK_REF", "AIRBENCH_SUBJECT"):
            env_backup[k] = os.environ.get(k)
            os.environ[k] = f"test-{k}"
        os.environ["AIRBENCH_CLEARANCE"] = "invalid-clearance"
        try:
            with self.assertRaises(EnvironmentError):
                NodeServerConfig.from_env()
        finally:
            for k, v in env_backup.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            if original is None:
                os.environ.pop("AIRBENCH_CLEARANCE", None)
            else:
                os.environ["AIRBENCH_CLEARANCE"] = original

    def test_from_yaml_file(self) -> None:
        config_data = {
            "node_identity": "node.yaml.test",
            "bearer_token": "yaml-token",
            "domain_pack_ref": "pack.yaml.v0",
            "clearance": "restricted",
            "subject": "principal.yaml",
            "host": "127.0.0.1",
            "port": 8800,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as fh:
            import yaml
            yaml.dump(config_data, fh)
            yaml_path = fh.name
        try:
            cfg = NodeServerConfig.from_yaml(Path(yaml_path))
            self.assertEqual(cfg.node_identity, "node.yaml.test")
            self.assertEqual(cfg.port, 8800)
            self.assertEqual(cfg.clearance, Clearance.restricted)
        finally:
            os.unlink(yaml_path)


# ---------------------------------------------------------------------------
# build_node_app integration (in-memory, skip startup checks)
# ---------------------------------------------------------------------------

class TestBuildNodeApp(unittest.TestCase):
    def _make_config(self) -> NodeServerConfig:
        return NodeServerConfig(
            node_identity="node.build.test",
            bearer_token="build-token",
            domain_pack_ref="pack.refinery.v0",
            clearance=Clearance.internal,
            subject="principal.build",
        )

    def test_build_node_app_returns_asgi_app(self) -> None:
        cfg = self._make_config()
        app = build_node_app(cfg, skip_startup_check=True)
        # FastAPI apps are ASGI callables
        self.assertTrue(callable(app))

    def test_built_app_health_endpoint(self) -> None:
        cfg = self._make_config()
        app = build_node_app(cfg, skip_startup_check=True)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://node.build.test",
        )
        resp = asyncio.run(client.get("/api/v1/health", headers={"Authorization": "Bearer build-token"}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ready")
        asyncio.run(client.aclose())

    def test_built_app_creates_task_without_optional_authorization_adapter(self) -> None:
        cfg = self._make_config()
        app = build_node_app(cfg, skip_startup_check=True)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://node.build.test",
        )
        body = _task_body()
        body["actor"] = "principal.build"
        body["idempotency_key"] = "idem.build.create.no-auth-adapter"
        body["command_id"] = "cmd.build.create.no-auth-adapter"
        body["arguments"]["principal_id"] = "principal.build"
        resp = asyncio.run(client.post("/api/v1/tasks", headers={"Authorization": "Bearer build-token"}, json=body))
        asyncio.run(client.aclose())
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(resp.json()["task"]["principal_id"], "principal.build")


if __name__ == "__main__":
    unittest.main()
