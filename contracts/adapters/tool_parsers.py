"""Model-specific tool-call parsers for local backend adapters.

Different model families emit tool calls in different text formats.
The router selects a model via the registry's ``tool_call_parser`` field
(e.g. ``"hermes"``, ``"standard_json"``, ``"none"``).  This module
translates that identifier into a typed parser that converts raw model
text or structured JSON into a tuple of :class:`BackendToolCall` objects.

Architecture note
-----------------
The parsers are **stateless** and **deterministic** — they never call the
network and never mutate shared state.  They are instantiated once per
adapter and reused across requests.  Parsing failure produces a typed
:class:`BackendCallError` rather than raising a bare exception, so the
orchestrator always sees a clean error code and retry guidance.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..backend import BackendCallError, BackendTool, BackendToolCall


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class BaseToolParser(ABC):
    """Parse raw model output into typed tool calls.

    Parameters
    ----------
    declared_tools:
        The tools advertised in the request.  A parser **must** reject any
        tool call whose name is not in this set — an unknown name is a
        contract violation, not a graceful degradation.
    """

    @abstractmethod
    def parse(
        self,
        raw_text: str,
        declared_tools: "tuple[BackendTool, ...]",
    ) -> "tuple[BackendToolCall, ...]":
        """Return zero or more validated tool calls extracted from *raw_text*.

        Raises :class:`~contracts.backend.BackendCallError` with
        ``code=malformed_response`` when the model output is syntactically
        invalid, references an undeclared tool, or contains contradictory
        structure.
        """


# ---------------------------------------------------------------------------
# Hermes / chatml tool-call parser (Qwen3-Coder, Qwen2.5-VL style)
# ---------------------------------------------------------------------------

#: Pattern matching ``<tool_call>\n{...}\n</tool_call>`` blocks emitted by
#: models trained with the Hermes/chatml format.
_HERMES_BLOCK = re.compile(
    r"<tool_call>\s*(\{.*?})\s*</tool_call>",
    re.DOTALL,
)


class HermesToolParser(BaseToolParser):
    """Parse Hermes-format ``<tool_call>{...}</tool_call>`` blocks.

    This is the canonical output format for:

    * ``Qwen3-Coder-30B-A3B-Instruct`` (AWQ INT4)
    * ``Qwen2.5-VL-7B-Instruct`` (AWQ INT4)

    Each block must contain valid JSON with at minimum a ``"name"`` key.
    Arguments are expected under ``"arguments"`` or ``"parameters"``; if
    absent an empty dict is used so downstream callers can distinguish
    "tool called with no args" from "tool not called".
    """

    def parse(
        self,
        raw_text: str,
        declared_tools: "tuple[BackendTool, ...]",
    ) -> "tuple[BackendToolCall, ...]":
        from ..backend import BackendCallError, BackendErrorCode, BackendFailure, BackendToolCall

        blocks = _HERMES_BLOCK.findall(raw_text)
        if not blocks:
            return ()

        declared_names = {tool.name for tool in declared_tools}
        results: list[BackendToolCall] = []

        for raw_block in blocks:
            try:
                data: dict[str, Any] = json.loads(raw_block)
            except json.JSONDecodeError as exc:
                raise BackendCallError(
                    BackendFailure(
                        code=BackendErrorCode.malformed_response,
                        message=f"hermes tool_call block is not valid JSON: {exc}",
                        retryable=False,
                        request_id="",
                        target_id="",
                    )
                ) from exc

            name = data.get("name") or data.get("tool")
            if not name or not isinstance(name, str):
                raise BackendCallError(
                    BackendFailure(
                        code=BackendErrorCode.malformed_response,
                        message="hermes tool_call block missing 'name' field",
                        retryable=False,
                        request_id="",
                        target_id="",
                    )
                )

            if name not in declared_names:
                raise BackendCallError(
                    BackendFailure(
                        code=BackendErrorCode.malformed_response,
                        message=f"model emitted tool call for undeclared tool '{name}'",
                        retryable=False,
                        request_id="",
                        target_id="",
                    )
                )

            arguments: dict[str, Any] = (
                data.get("arguments")
                or data.get("parameters")
                or {}
            )
            if not isinstance(arguments, dict):
                raise BackendCallError(
                    BackendFailure(
                        code=BackendErrorCode.malformed_response,
                        message=f"hermes tool_call arguments for '{name}' must be an object",
                        retryable=False,
                        request_id="",
                        target_id="",
                    )
                )

            results.append(BackendToolCall(name=name, arguments=arguments))

        return tuple(results)


# ---------------------------------------------------------------------------
# Standard OpenAI-compat JSON tool-call parser (Gemma 4 / generic)
# ---------------------------------------------------------------------------

class StandardJsonToolParser(BaseToolParser):
    """Parse the OpenAI-compatible ``tool_calls`` JSON array.

    This is returned by vLLM and NIM when the model natively produces
    tool calls in OpenAI format (Gemma 4 31B / 26B A4B instruction-tuned
    targets).  The adapter passes the parsed ``tool_calls`` list directly
    to this parser.
    """

    def parse(
        self,
        raw_text: str,
        declared_tools: "tuple[BackendTool, ...]",
    ) -> "tuple[BackendToolCall, ...]":
        from ..backend import BackendCallError, BackendErrorCode, BackendFailure, BackendToolCall

        if not raw_text.strip():
            return ()

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise BackendCallError(
                BackendFailure(
                    code=BackendErrorCode.malformed_response,
                    message=f"standard_json tool_calls is not valid JSON: {exc}",
                    retryable=False,
                    request_id="",
                    target_id="",
                )
            ) from exc

        if not isinstance(data, list):
            raise BackendCallError(
                BackendFailure(
                    code=BackendErrorCode.malformed_response,
                    message="standard_json tool_calls must be a JSON array",
                    retryable=False,
                    request_id="",
                    target_id="",
                )
            )

        declared_names = {tool.name for tool in declared_tools}
        results: list[BackendToolCall] = []

        for item in data:
            if not isinstance(item, dict):
                raise BackendCallError(
                    BackendFailure(
                        code=BackendErrorCode.malformed_response,
                        message="each tool_call item must be an object",
                        retryable=False,
                        request_id="",
                        target_id="",
                    )
                )

            # OpenAI format: {"type": "function", "function": {"name": ..., "arguments": "..."}}
            function_block = item.get("function") or item
            name = function_block.get("name")
            if not name or not isinstance(name, str):
                raise BackendCallError(
                    BackendFailure(
                        code=BackendErrorCode.malformed_response,
                        message="tool_call item missing function name",
                        retryable=False,
                        request_id="",
                        target_id="",
                    )
                )

            if name not in declared_names:
                raise BackendCallError(
                    BackendFailure(
                        code=BackendErrorCode.malformed_response,
                        message=f"model emitted tool call for undeclared tool '{name}'",
                        retryable=False,
                        request_id="",
                        target_id="",
                    )
                )

            raw_args = function_block.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    arguments: dict[str, Any] = json.loads(raw_args)
                except json.JSONDecodeError as exc:
                    raise BackendCallError(
                        BackendFailure(
                            code=BackendErrorCode.malformed_response,
                            message=f"tool arguments for '{name}' are not valid JSON: {exc}",
                            retryable=False,
                            request_id="",
                            target_id="",
                        )
                    ) from exc
            else:
                arguments = raw_args if isinstance(raw_args, dict) else {}

            results.append(BackendToolCall(name=name, arguments=arguments))

        return tuple(results)


# ---------------------------------------------------------------------------
# Null parser (embedding / reranker — no tool calls)
# ---------------------------------------------------------------------------

class NoneToolParser(BaseToolParser):
    """Always returns an empty tuple.

    Used for embedding and reranking services that never emit tool calls.
    If the model text contains anything that looks like a tool call block
    it is silently ignored; the caller determines whether a non-empty text
    response is valid.
    """

    def parse(
        self,
        raw_text: str,
        declared_tools: "tuple[BackendTool, ...]",
    ) -> "tuple[BackendToolCall, ...]":
        return ()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_PARSERS: dict[str, type[BaseToolParser]] = {
    "hermes": HermesToolParser,
    "standard_json": StandardJsonToolParser,
    "none": NoneToolParser,
}


class ToolCallParserRegistry:
    """Map the ``tool_call_parser`` field from a :class:`ModelTarget` to a parser.

    The registry is a lightweight lookup table; it never performs I/O or
    mutates shared state.  Requesting an unknown parser ID raises
    :class:`~contracts.backend.BackendCallError` with
    ``code=unsupported_capability`` so the router can record a typed failure.
    """

    @staticmethod
    def get(parser_id: str) -> BaseToolParser:
        """Return an instantiated parser for *parser_id*.

        Parameters
        ----------
        parser_id:
            The ``tool_call_parser`` value from the model roster entry
            (e.g. ``"hermes"``, ``"standard_json"``, ``"none"``).

        Raises
        ------
        BackendCallError
            ``code=unsupported_capability``, ``retryable=False`` when no
            parser is registered for *parser_id*.
        """
        from ..backend import BackendCallError, BackendErrorCode, BackendFailure

        cls = _PARSERS.get(parser_id.lower() if isinstance(parser_id, str) else "")
        if cls is None:
            raise BackendCallError(
                BackendFailure(
                    code=BackendErrorCode.unsupported_capability,
                    message=f"no tool-call parser registered for id '{parser_id}'; "
                            f"known parsers: {sorted(_PARSERS)}",
                    retryable=False,
                    request_id="",
                    target_id="",
                )
            )
        return cls()

    @staticmethod
    def known_ids() -> tuple[str, ...]:
        """Return all registered parser IDs (sorted)."""
        return tuple(sorted(_PARSERS))


__all__ = [
    "BaseToolParser",
    "HermesToolParser",
    "NoneToolParser",
    "StandardJsonToolParser",
    "ToolCallParserRegistry",
]
