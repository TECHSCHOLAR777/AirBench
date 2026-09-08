import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from airbench.tools.podman_provider import PodmanProvider
from airbench.tools.sandbox import SandboxExecutionRequest, SandboxError


IMAGE = "docker.io/library/python@sha256:" + "a" * 64


class PodmanProviderTests(unittest.TestCase):
    def test_runtime_version_accepts_local_client_identity(self):
        self.assertEqual(
            PodmanProvider._runtime_version({"Client": {"Version": "5.7.0"}}),
            "5.7.0",
        )

    def test_only_content_addressed_images_are_accepted(self):
        with self.assertRaises(SandboxError) as caught:
            PodmanProvider("docker.io/library/python:3.11-slim")
        self.assertEqual(caught.exception.code, "unverified_image")

    def test_capabilities_include_hard_boundary_and_resource_controls(self):
        provider = PodmanProvider(IMAGE, expected_runtime_version="6.1.1")
        self.assertFalse(provider.capabilities.hard_network_isolation)
        provider._verification_digest = "verified-for-unit-test"
        capabilities = provider.capabilities
        self.assertTrue(capabilities.hard_network_isolation)
        self.assertTrue(capabilities.hard_filesystem_isolation)
        self.assertTrue(capabilities.non_root_execution)
        self.assertTrue(capabilities.restricted_syscalls)
        self.assertEqual(
            set(capabilities.resource_limits),
            {"code_bytes", "output_bytes", "wall_time", "cpu_time", "memory", "disk", "processes"},
        )

    def test_build_command_is_explicit_and_never_pulls_or_uses_default_network(self):
        provider = PodmanProvider(IMAGE)
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            request = SandboxExecutionRequest(
                command=("/usr/bin/python", "-I", "-c", "worker"),
                cwd=root_path,
                environment={"PATH": "ignored", "PYTHONUNBUFFERED": "1"},
                stdin="{}",
                timeout_seconds=3,
                max_output_bytes=4096,
                root_dir=root_path,
                read_paths=(),
                write_paths=(),
                resource_limits={
                    "max_wall_seconds": 3.0,
                    "max_output_bytes": 4096,
                    "max_code_bytes": 1024,
                    "max_cpu_seconds": 2.0,
                    "max_memory_bytes": 16 * 1024 * 1024,
                    "max_disk_bytes": 32 * 1024 * 1024,
                    "max_processes": 8,
                },
            )
            with patch("airbench.tools.podman_provider.os.name", "posix"):
                command, limits, name = provider.build_command(request)
        self.assertEqual(command[0], "podman")
        self.assertIn("--pull=never", command)
        self.assertIn("--network=none", command)
        self.assertIn("--read-only", command)
        self.assertIn("--cap-drop=ALL", command)
        self.assertIn("--security-opt=no-new-privileges", command)
        self.assertIn("--user", command)
        self.assertIn("65532:65532", command)
        self.assertIn("--ulimit", command)
        self.assertIn("cpu=2", command)
        self.assertIn("--memory", command)
        self.assertIn(str(16 * 1024 * 1024), command)
        self.assertIn("--storage-opt", command)
        self.assertIn("size=" + str(32 * 1024 * 1024), command)
        self.assertIn("--pids-limit", command)
        self.assertIn("8", command)
        self.assertEqual(limits["max_cpu_seconds"], 2.0)
        self.assertTrue(name.startswith("airbench-sbx-"))
        self.assertEqual(command[-5:], (IMAGE, "/usr/local/bin/python", "-I", "-c", "worker"))

    def test_windows_host_fails_closed_instead_of_mis_mapping_paths(self):
        provider = PodmanProvider(IMAGE)
        with patch("airbench.tools.podman_provider.os.name", "nt"):
            with self.assertRaises(SandboxError) as caught:
                provider.verify()
        self.assertEqual(caught.exception.code, "provider_host_unsupported")


if __name__ == "__main__":
    unittest.main()
