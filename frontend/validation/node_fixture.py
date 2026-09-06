"""Synthetic AirBench Node for local desktop validation only.

This fixture is deliberately small. It authenticates a bearer token, exposes
the handshake contract, and writes redacted JSONL logs. It does not parse user
files, call models, or represent a production Node.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import ssl
import sys
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def fixture_events() -> list[dict[str, object]]:
    base = {
        "taskId": "task-fixture",
        "schemaVersion": "0.1",
        "occurredAt": "2026-09-06T00:00:00Z",
        "actor": "fixture-node",
        "clearanceContext": "restricted",
    }
    return [
        {**base, "eventId": "event-1", "sequence": 1, "eventType": "task.accepted", "payloadHash": "hash-1", "ledgerEventRef": "ledger-task-1", "payload": {"phase": "accepted", "status": "accepted"}},
        {**base, "eventId": "event-2", "sequence": 2, "eventType": "worker.started", "payloadHash": "hash-2", "ledgerEventRef": "ledger-worker-2", "payload": {"role": "planner", "label": "Plan task", "status": "running"}},
        {**base, "eventId": "event-3", "sequence": 3, "eventType": "tool.completed", "payloadHash": "hash-3", "ledgerEventRef": "ledger-tool-3", "payload": {"role": "file_intake", "label": "Read report", "status": "completed"}},
        {**base, "eventId": "event-4", "sequence": 4, "eventType": "approval.required", "payloadHash": "hash-4", "ledgerEventRef": "ledger-approval-4", "payload": {"reason": "Approval note is ready for review"}},
        {**base, "eventId": "event-5", "sequence": 5, "eventType": "artifact.ready", "payloadHash": "hash-5", "ledgerEventRef": "ledger-artifact-5", "payload": {"artifactId": "artifact-approval-note"}},
    ]


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "AirBenchFixture/0.1"

    def log_message(self, format: str, *args: object) -> None:
        self.server.log_event({"event": "http", "message": format % args})  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        expected_token = self.server.expected_token  # type: ignore[attr-defined]
        provided = self.headers.get("Authorization", "")
        if provided != f"Bearer {expected_token}":
            self.server.log_event({"event": "auth_rejected", "path": self.path})  # type: ignore[attr-defined]
            self._json(401, {"error": "unauthorized"})
            return

        handshake_path = "/api/v1/node/handshake"
        parsed = urlparse(self.path)
        if parsed.path == "/api/v1/tasks/task-fixture/events":
            query = parse_qs(parsed.query)
            try:
                after_sequence = int(query.get("after_sequence", ["0"])[0])
            except ValueError:
                self._json(400, {"error": "invalid_cursor"})
                return
            events = [event for event in fixture_events() if int(event["sequence"]) > after_sequence]
            self.server.log_event(  # type: ignore[attr-defined]
                {"event": "events_returned", "task_id": "task-fixture", "after_sequence": str(after_sequence), "count": str(len(events))}
            )
            self._json(200, {
                "stream_id": "task-fixture",
                "node_identity": self.server.node_identity,  # type: ignore[attr-defined]
                "protocol_version": self.server.protocol_version,  # type: ignore[attr-defined]
                "clearance_context": self.server.clearance_context,  # type: ignore[attr-defined]
                "events": events,
                "next_sequence": max([after_sequence, *[int(event["sequence"]) for event in events]]),
                "has_more": False,
                "ledger_event_refs": [str(event["ledgerEventRef"]) for event in events],
            })
            return

        if parsed.path.startswith("/api/v1/intake/") and parsed.path.endswith("/preview"):
            intake_id = parsed.path.split("/")[4]
            manifest = self.server.intakes.get(intake_id)  # type: ignore[attr-defined]
            if manifest is None:
                self._json(404, {"error": "unknown_intake"})
                return
            self._json(200, {
                "preview_ref": manifest["preview_ref"],
                "preview_kind": "text",
                "text": "Synthetic scanned-document page preview. The source remains untrusted data and was not executed.",
                "source_hash": manifest["source_hash"],
                "source_region": "page:1;region:full-page",
                "confidence": 0.98,
                "clearance": manifest["clearance"],
                "taint": manifest["taint"],
                "ledger_event_ref": "fixture-ledger-preview-001",
            })
            return

        if parsed.path == "/api/v1/artifacts/artifact-approval-note/preview":
            self._json(200, {
                "artifact_id": "artifact-approval-note",
                "preview_kind": "structured_document",
                "title": "Inspection approval note",
                "blocks": [
                    {"kind": "heading", "text": "Approval note"},
                    {"kind": "paragraph", "text": "Synthetic fixture artifact preview. Values are supplied by the Node artifact contract."},
                ],
                "clearance": "restricted",
                "taint": "untrusted",
                "ledger_event_ref": "fixture-ledger-artifact-preview-001",
            })
            return

        if parsed.path == "/api/v1/artifacts/artifact-approval-note/download":
            if self.server.deny_download:  # type: ignore[attr-defined]
                self._json(403, {"error": "clearance_denied"})
                return
            pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(pdf)))
            self.send_header("X-AirBench-Artifact-Hash", f"sha256:{hashlib.sha256(pdf).hexdigest()}")
            self.send_header("X-AirBench-Ledger-Event-Ref", "fixture-ledger-download-001")
            self.end_headers()
            self.wfile.write(pdf)
            self.server.log_event({"event": "artifact_download_allowed", "artifact_id": "artifact-approval-note"})  # type: ignore[attr-defined]
            return

        if parsed.path != handshake_path:
            self.server.log_event({"event": "non_airbench_path", "path": self.path})  # type: ignore[attr-defined]
            self._json(404, {"error": "not_found"})
            return

        payload = {
            "node_identity": self.server.node_identity,  # type: ignore[attr-defined]
            "protocol_version": self.server.protocol_version,  # type: ignore[attr-defined]
            "clearance_context": self.server.clearance_context,  # type: ignore[attr-defined]
            "authenticated_subject": self.server.authenticated_subject,  # type: ignore[attr-defined]
            "ledger_event_ref": "fixture-ledger-connection-001",
        }
        self.server.log_event(  # type: ignore[attr-defined]
            {
                "event": "handshake_accepted",
                "path": self.path,
                "node_identity": self.server.node_identity,  # type: ignore[attr-defined]
                "authenticated_subject": self.server.authenticated_subject,  # type: ignore[attr-defined]
            }
        )
        self._json(200, payload)

    def do_POST(self) -> None:
        expected_token = self.server.expected_token  # type: ignore[attr-defined]
        if self.headers.get("Authorization", "") != f"Bearer {expected_token}":
            self.server.log_event({"event": "auth_rejected", "path": self.path})  # type: ignore[attr-defined]
            self._json(401, {"error": "unauthorized"})
            return
        if self.path != "/api/v1/intake/query-upload":
            self._json(404, {"error": "not_found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "invalid_content_length"})
            return
        if content_length <= 0 or content_length > 100 * 1024 * 1024:
            self._json(413, {"error": "upload_too_large"})
            return
        body = self.rfile.read(content_length)
        raw_message = b"Content-Type: " + self.headers.get("Content-Type", "").encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
        message = BytesParser(policy=default).parsebytes(raw_message)
        document = next((part for part in message.iter_attachments() if part.get_param("name", header="Content-Disposition") == "document"), None)
        if document is None:
            self._json(422, {"error": "document_part_missing"})
            return
        document_bytes = document.get_payload(decode=True) or b""
        if not document_bytes:
            self._json(422, {"error": "empty_document"})
            return
        file_name = os.path.basename(document.get_filename() or "uploaded-document")
        media_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        if not (file_name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"))):
            self._json(415, {"error": "unsupported_media_type"})
            return
        source_hash = f"sha256:{hashlib.sha256(document_bytes).hexdigest()}"
        short_hash = hashlib.sha256(document_bytes).hexdigest()[:16]
        intake_id = f"fixture-intake-{short_hash}"
        manifest = {
            "intake_id": intake_id,
            "file_name": file_name,
            "byte_size": len(document_bytes),
            "source_hash": source_hash,
            "revision_id": f"revision-{short_hash}",
            "media_type": media_type,
            "page_count": 1,
            "ocr_status": "completed",
            "vision_status": "completed",
            "clearance": "restricted",
            "taint": "untrusted",
            "preview_ref": intake_id,
            "artifact_ref": "artifact-approval-note",
            "ledger_event_ref": "fixture-ledger-intake-001",
        }
        self.server.intakes[intake_id] = manifest  # type: ignore[attr-defined]
        self.server.log_event({"event": "intake_created", "intake_id": intake_id, "source_hash": source_hash, "taint": "untrusted", "intake_mode": "query_upload"})  # type: ignore[attr-defined]
        self._json(200, manifest)

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FixtureServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], args: argparse.Namespace) -> None:
        super().__init__(address, FixtureHandler)
        self.expected_token = args.token
        self.node_identity = args.node_identity
        self.protocol_version = args.protocol_version
        self.clearance_context = args.clearance_context
        self.authenticated_subject = args.authenticated_subject
        self.log_path = args.log_path
        self.intakes: dict[str, dict[str, object]] = {}
        self.deny_download = args.deny_download

    def log_event(self, event: dict[str, str]) -> None:
        event = {"fixture": "airbench-node", **event}
        line = json.dumps(event, sort_keys=True)
        print(line, flush=True)
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", default="fixture-token")
    parser.add_argument("--node-identity", default="fixture-node-01")
    parser.add_argument("--protocol-version", default="0.1")
    parser.add_argument("--clearance-context", default="restricted")
    parser.add_argument("--authenticated-subject", default="fixture-user")
    parser.add_argument("--log-path", default="")
    parser.add_argument("--cert-path")
    parser.add_argument("--key-path")
    parser.add_argument("--deny-download", action="store_true")
    args = parser.parse_args()

    if bool(args.cert_path) != bool(args.key_path):
        parser.error("--cert-path and --key-path must be provided together")

    server = FixtureServer((args.bind, args.port), args)
    if args.cert_path:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.cert_path, args.key_path)
        server.socket = context.wrap_socket(server.socket, server_side=True)

    scheme = "https" if args.cert_path else "http"
    server.log_event({"event": "ready", "endpoint": f"{scheme}://{args.bind}:{args.port}"})
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
