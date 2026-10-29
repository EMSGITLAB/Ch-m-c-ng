import importlib.util
import socket
from pathlib import Path

import pytest


def test_guard_blocks_dns_tcp_and_udp_without_real_egress():
    # Load under a non-plugin name so this unit test controls its own guard.
    spec = importlib.util.spec_from_file_location("test_guard_module", Path(__file__).with_name("network_guard.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    guard = module.NetworkGuard().install()
    try:
        with pytest.raises(AssertionError):
            socket.getaddrinfo("example.invalid", 443)
        with socket.socket() as sock, pytest.raises(AssertionError):
            sock.connect(("192.0.2.1", 443))
        with socket.socket(type=socket.SOCK_DGRAM) as sock, pytest.raises(AssertionError):
            sock.sendto(b"must-not-leave", ("192.0.2.1", 443))
        assert guard.denied == 3
        assert socket.gethostbyname("localhost") == "127.0.0.1"
    finally:
        guard.close()
