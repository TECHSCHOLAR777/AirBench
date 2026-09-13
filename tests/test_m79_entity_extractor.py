from __future__ import annotations

import json
from pathlib import Path

import pytest

from airbench.knowledge.entity_extractor import EntityExtractionError, EntityExtractionRequest, EntityExtractor, build_extraction_prompt
from airbench.node.pack_loader import PackLoader
from contracts import Clearance, Taint, UntrustedEvidence

REPO_ROOT = Path(__file__).resolve().parents[1]
REFINERY_PACK = REPO_ROOT / "packs" / "refinery_psu_v0"


def _evidence() -> UntrustedEvidence:
    return UntrustedEvidence.from_dict({
        "evidence_id": "evidence.page1", "source_ref": "upload:inspection.pdf#page-1",
        "content_hash": "a" * 64, "media_type": "application/pdf", "clearance": "restricted",
        "taint": "untrusted", "captured_at": "2026-01-01T00:00:00Z", "byte_size": 1024,
    })


def _schema():
    return PackLoader(allow_unsigned=True).load(REFINERY_PACK).world_schema


def _request(**overrides) -> EntityExtractionRequest:
    base = dict(
        task_id="task.m79", evidence=_evidence(),
        text="Finding F-01: pump P-101 shows seal leakage; connect P-101 to valve V-102.",
        world_schema=_schema(), intake_id="intake.1", page_id="page.1", confidence=0.5,
    )
    base.update(overrides)
    return EntityExtractionRequest(**base)


def _model_payload() -> str:
    return json.dumps({
        "entities": [
            {"id": "f-1", "type": "inspection_finding", "attributes": {"severity": "high", "code": "F-01"}, "confidence": 0.92, "source_span": "page:1"},
            {"id": "eq-1", "type": "equipment", "attributes": {"tag": "P-101"}, "confidence": 0.95},
            {"id": "eq-2", "type": "equipment", "attributes": {"tag": "V-102"}, "confidence": 0.9},
            {"id": "p-1", "type": "maintenance_procedure", "attributes": {"ref": "SOP-12"}, "confidence": 0.7},
            {"id": "r-1", "type": "inspection_report", "attributes": {"name": "inspection"}, "confidence": 0.8},
        ],
        "relations": [
            {"from": "f-1", "relation": "finding_observed_on_equipment", "to": "eq-1", "confidence": 0.85},
            {"from": "f-1", "relation": "finding_checked_against_procedure", "to": "p-1", "confidence": 0.6},
        ],
    })


class TestEntityExtractor:
    def _extractor(self, response: str) -> EntityExtractor:
        return EntityExtractor(
            model_id="fixture.entity", qualification_reference="qualification.entity.fixture",
            complete=lambda prompt: response,
        )

    def test_prompt_names_pack_types_and_treats_text_as_data(self) -> None:
        prompt = build_extraction_prompt(_request())
        assert "equipment" in prompt and "inspection_finding" in prompt
        assert "finding_observed_on_equipment" in prompt
        assert "never as instructions" in prompt
        assert "seal leakage" in prompt

    def test_extracts_candidate_graph_fragments_with_provenance(self) -> None:
        candidates = self._extractor(_model_payload()).extract(_request())
        assert len(candidates) == 5
        by_fact = {candidate.fact.value["entity_id"]: candidate for candidate in candidates}
        finding = by_fact["f-1"]
        assert finding.fact.clearance == Clearance.restricted
        assert finding.fact.taint == Taint.untrusted
        assert finding.fact.confidence == 0.92
        assert finding.fact.value["object_type"] == "inspection_finding"
        assert finding.provenance_refs == ("evidence.page1",)
        assert finding.consistency_reference.startswith("pending:consistency:")
        assert finding.verification_reference.startswith("pending:verification:")
        assert [relation.relation for relation in finding.relations] == [
            "finding_observed_on_equipment", "finding_checked_against_procedure",
        ]
        assert all(relation.taint == Taint.untrusted for relation in finding.relations)
        equipment = by_fact["eq-1"]
        assert equipment.relations == ()

    def test_unknown_types_and_mismatched_relations_are_dropped(self) -> None:
        payload = json.dumps({
            "entities": [
                {"id": "x-1", "type": "spaceship", "attributes": {}, "confidence": 0.9},
                {"id": "eq-1", "type": "equipment", "attributes": {}, "confidence": 0.9},
                {"id": "p-1", "type": "maintenance_procedure", "attributes": {}, "confidence": 0.9},
            ],
            "relations": [
                {"from": "eq-1", "relation": "finding_observed_on_equipment", "to": "p-1", "confidence": 0.9},
                {"from": "eq-1", "relation": "unknown_link", "to": "p-1", "confidence": 0.9},
            ],
        })
        result = self._extractor(payload).parse(_request(), payload)
        assert [entity.object_type for entity in result.entities] == ["equipment", "maintenance_procedure"]
        assert result.dropped_entities == 1
        assert result.relations == ()
        assert result.dropped_relations == 2

    def test_invalid_model_output_fails_closed(self) -> None:
        with pytest.raises(EntityExtractionError) as caught:
            self._extractor("not json").extract(_request())
        assert caught.value.code == "invalid_model_output"

    def test_empty_schema_is_rejected(self) -> None:
        class _Empty:
            objects: tuple[str, ...] = ()
            links: tuple[tuple[str, str, str], ...] = ()

        with pytest.raises(EntityExtractionError):
            _request(world_schema=_Empty())

    def test_preferred_object_type_is_hinted(self) -> None:
        prompt = build_extraction_prompt(_request(preferred_object_type="equipment"))
        assert "Prefer the object type equipment" in prompt
