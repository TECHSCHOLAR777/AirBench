from __future__ import annotations

import pytest

from airbench.node.no_egress import NoEgressError, external, is_loopback, observe_no_egress


def test_loopback_detection() -> None:
    assert is_loopback("127.0.0.1:8001")
    assert is_loopback("[::1]:8001")
    assert not is_loopback("10.0.0.5:443")
    assert not is_loopback("142.250.1.1:443")


def test_external_filters_loopback() -> None:
    connections = (
        ("127.0.0.1:5000", "127.0.0.1:8001"),
        ("0.0.0.0:5000", "142.250.1.1:443"),
        ("127.0.0.1:6000", "[::1]:8002"),
    )
    assert external(connections) == ("142.250.1.1:443",)


def test_observe_clean_and_dirty() -> None:
    clean = observe_no_egress(lister=lambda: [("127.0.0.1:1", "127.0.0.1:2")])
    assert clean.clean is True
    assert clean.checked == 1

    dirty = observe_no_egress(lister=lambda: [("127.0.0.1:1", "8.8.8.8:53")])
    assert dirty.clean is False
    assert dirty.external_connections == ("8.8.8.8:53",)


def test_observation_failure_is_typed() -> None:
    def boom():
        raise OSError("no lister")

    with pytest.raises(NoEgressError):
        observe_no_egress(lister=boom)
