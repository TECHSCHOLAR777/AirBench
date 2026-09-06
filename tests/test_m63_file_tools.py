import tempfile
import unittest
from pathlib import Path

from airbench.file_tools import (FileProvenance, FileToolError, FileToolRunner,
                                  SpreadsheetTable, SpreadsheetTool, WorkspacePolicy)
from contracts import Clearance, EventLedger, Taint, build_event


TASK_ID = "task.file-tools-001"


def task_created(ledger):
    ledger.append(build_event(
        event_type="task.created", task_id=TASK_ID, actor_id="test.user", actor_type="principal",
        payload_contract="TaskEnvelope", payload_version="1.0", payload={"request": "test"},
        clearance=Clearance.internal, idempotency="task-created", sequence=0,
    ))


class FileToolTests(unittest.TestCase):
    def test_read_write_and_inspect_are_scoped_and_provenance_bearing(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as source:
            root_path = Path(root)
            source_path = Path(source) / "inspection.bin"
            source_path.write_bytes(b"untrusted bytes")
            runner = FileToolRunner(ledger, WorkspacePolicy(root_path, (Path(source),)))
            read = runner.read(task_id=TASK_ID, operation_id="read-1", path=str(source_path), clearance=Clearance.internal)
            self.assertEqual(read.content, b"untrusted bytes")
            self.assertEqual(read.provenance.taint, Taint.untrusted)
            written = runner.write(
                task_id=TASK_ID, operation_id="write-1", path=str(root_path / "artifact.txt"),
                content=b"generated", provenance=FileProvenance("derived:code", 1.0, Clearance.internal, Taint.untrusted),
            )
            inspection = runner.inspect(task_id=TASK_ID, operation_id="inspect-1", path=str(root_path / "artifact.txt"), clearance=Clearance.internal)
            self.assertEqual(written.content_hash, inspection.content_hash)
            self.assertEqual(inspection.media_type, "text/plain")
            self.assertEqual([event.event_type for event in ledger.events], [
                "task.created", "artifact.checked", "artifact.staged", "artifact.checked", "artifact.checked",
            ])

    def test_traversal_and_size_limits_fail_closed(self):
        ledger = EventLedger()
        task_created(ledger)
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            runner = FileToolRunner(ledger, WorkspacePolicy(Path(root), max_read_bytes=3, max_write_bytes=3))
            outside_file = Path(outside) / "outside.txt"
            outside_file.write_bytes(b"no")
            with self.assertRaises(FileToolError):
                runner.read(task_id=TASK_ID, operation_id="outside", path=str(outside_file), clearance=Clearance.internal)
            with self.assertRaises(FileToolError):
                runner.write(
                    task_id=TASK_ID, operation_id="large", path=str(Path(root) / "large.txt"), content=b"1234",
                    provenance=FileProvenance("derived:test", 1.0, Clearance.internal, Taint.clean),
                )
        self.assertEqual(len(ledger.events), 1)

    def test_spreadsheet_operations_use_typed_rows_and_compute_deterministically(self):
        ledger = EventLedger()
        task_created(ledger)
        provenance = FileProvenance("intake:table-1", 0.91, Clearance.restricted, Taint.untrusted)
        table = SpreadsheetTable(
            columns=("item", "amount"),
            rows=(("A", "1.25"), ("B", "2.75"), ("A", "3")),
            provenance=provenance,
            revision_id="revision.table-1",
        )
        tool = SpreadsheetTool(ledger)
        filtered = tool.filter_equals(task_id=TASK_ID, operation_id="filter-1", table=table, column="item", value="A")
        selected = tool.select_columns(task_id=TASK_ID, operation_id="select-1", table=filtered, columns=("amount",))
        total = tool.sum_column(task_id=TASK_ID, operation_id="sum-1", table=selected, column="amount", name="total_amount")
        self.assertEqual(filtered.rows, (("A", "1.25"), ("A", "3")))
        self.assertEqual(total.value_text, "4.25")
        self.assertEqual(total.provenance.taint, Taint.untrusted)
        self.assertEqual(total.provenance.clearance, Clearance.restricted)
        self.assertEqual(len(ledger.events), 4)

    def test_table_shape_and_non_numeric_sum_are_rejected(self):
        ledger = EventLedger()
        task_created(ledger)
        provenance = FileProvenance("intake:table-2", 1.0, Clearance.internal, Taint.untrusted)
        tool = SpreadsheetTool(ledger)
        malformed = SpreadsheetTable(("amount",), ((1, 2),), provenance, "revision.bad")
        with self.assertRaises(FileToolError):
            tool.sum_column(task_id=TASK_ID, operation_id="bad-shape", table=malformed, column="amount", name="total")
        non_numeric = SpreadsheetTable(("amount",), (("not-a-number",),), provenance, "revision.bad-2")
        with self.assertRaises(FileToolError):
            tool.sum_column(task_id=TASK_ID, operation_id="bad-number", table=non_numeric, column="amount", name="total")


if __name__ == "__main__":
    unittest.main()
