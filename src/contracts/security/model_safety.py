"""Deterministic pre-model safety gates for high-risk operational requests.

The gate is deliberately narrow.  It blocks explicit requests for procedural
instructions that would bypass a safety control, while allowing ordinary
discussion, incident analysis, and safe refusal text to reach the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_PROCEDURE = re.compile(r"\b(?:step(?:s)?|instruction(?:s)?|procedure|how\s+to|walk\s+me\s+through)\b", re.IGNORECASE)
_CONTROL = re.compile(r"\b(?:safety\s+interlock|safety\s+guard|protective\s+trip|lockout|safety\s+control)\b", re.IGNORECASE)
_DEFEAT = re.compile(r"\b(?:bypass|disable|defeat|circumvent|override|defeating|bypassing)\b", re.IGNORECASE)
_REFUSAL = re.compile(r"\b(?:cannot|can't|unable|won't|will not|refuse|not able)\b", re.IGNORECASE)
_STEP = re.compile(r"\bstep\s*\d+\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    allowed: bool
    reason: str = ""


def evaluate_model_text(text: str) -> SafetyDecision:
    """Return a policy decision without sending ``text`` to a model.

    Only the conjunction of an explicit procedural request, a named safety
    control, and a defeat verb is blocked.  The original text is never
    included in the decision reason or any ledger payload.
    """

    normalized = str(text or "")
    if _REFUSAL.search(normalized) and not _STEP.search(normalized):
        return SafetyDecision(True)
    if _PROCEDURE.search(normalized) and _CONTROL.search(normalized) and _DEFEAT.search(normalized):
        return SafetyDecision(False, "procedural safety-control bypass request")
    return SafetyDecision(True)


def evaluate_model_messages(messages: object) -> SafetyDecision:
    """Evaluate text parts in provider-neutral model messages."""

    for message in messages if isinstance(messages, (tuple, list)) else ():
        content = getattr(message, "content", ())
        for part in content if isinstance(content, (tuple, list)) else ():
            decision = evaluate_model_text(getattr(part, "text", "") or "")
            if not decision.allowed:
                return decision
    return SafetyDecision(True)


__all__ = ["SafetyDecision", "evaluate_model_messages", "evaluate_model_text"]
