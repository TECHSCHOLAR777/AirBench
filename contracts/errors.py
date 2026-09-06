from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str
    message: str
    value_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"path": self.path, "code": self.code, "message": self.message}
        if self.value_type is not None:
            result["value_type"] = self.value_type
        return result


class ContractValidationError(ValueError):
    """Stable machine-readable validation failure; never includes secret values."""

    def __init__(self, contract: str, issues: list[ValidationIssue]):
        self.contract = contract
        self.issues = tuple(issues)
        super().__init__(f"{contract} rejected: {len(issues)} validation issue(s)")

    def to_dict(self) -> dict[str, Any]:
        return {"error": "contract_validation_failed", "contract": self.contract, "issues": [i.to_dict() for i in self.issues]}
