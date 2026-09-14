"""Provider-specific backend adapters for AirBench.

All adapters conform to the :class:`contracts.backend.BackendAdapter` protocol
and translate provider HTTP responses into the provider-neutral
:class:`contracts.backend.BackendResponse` / :class:`contracts.backend.BackendChunk`
shapes.  No provider payload object ever crosses the contract boundary.
"""

from .tool_parsers import (
    BaseToolParser,
    HermesToolParser,
    NoneToolParser,
    StandardJsonToolParser,
    ToolCallParserRegistry,
)
from .vllm_adapter import VllmAdapter
from .nim_adapter import NimAdapter
from .remote_adapter import FakeRemoteEndpoint, RemoteEndpointAdapter

__all__ = [
    "BaseToolParser",
    "HermesToolParser",
    "NoneToolParser",
    "StandardJsonToolParser",
    "ToolCallParserRegistry",
    "VllmAdapter",
    "NimAdapter",
    "FakeRemoteEndpoint",
    "RemoteEndpointAdapter",
]
