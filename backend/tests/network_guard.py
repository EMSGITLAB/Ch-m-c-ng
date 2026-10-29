"""Test-process egress guard; leaves the user's actual network untouched."""

import ipaddress
import socket
from contextlib import ExitStack
from unittest.mock import patch


class NetworkGuard:
    def __init__(self):
        self.denied = 0
        self.patches = ExitStack()

    def host(self, value):
        if value is None or value in {"", "localhost", b"localhost"}:
            return
        try:
            if ipaddress.ip_address(value.decode() if isinstance(value, bytes) else value).is_loopback:
                return
        except ValueError:
            pass
        self.denied += 1
        raise AssertionError("Nonlocal networking is forbidden in this offline test process")

    def install(self):
        connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
        sendto, resolve = socket.socket.sendto, socket.getaddrinfo
        guard = self

        def address(sock, value):
            if sock.family == getattr(socket, "AF_UNIX", None):
                return value
            guard.host(value[0])
            return ("127.0.0.1", *value[1:]) if value[0] == "localhost" else value

        def guarded_connect(sock, value):
            return connect(sock, address(sock, value))

        def guarded_connect_ex(sock, value):
            return connect_ex(sock, address(sock, value))

        def guarded_sendto(sock, *args):
            address(sock, args[-1])
            return sendto(sock, *args)

        def guarded_resolve(host, *args, **kwargs):
            guard.host(host)
            return resolve("127.0.0.1" if host == "localhost" else host, *args, **kwargs)

        def ipv4(host):
            guard.host(host)
            return "127.0.0.1" if host == "localhost" else host

        def names(host):
            return "localhost", [], [ipv4(host)]

        for target, replacement in (("socket.socket.connect", guarded_connect),
                                    ("socket.socket.connect_ex", guarded_connect_ex),
                                    ("socket.socket.sendto", guarded_sendto),
                                    ("socket.getaddrinfo", guarded_resolve),
                                    ("socket.gethostbyname", ipv4),
                                    ("socket.gethostbyname_ex", names),
                                    ("socket.gethostbyaddr", names)):
            self.patches.enter_context(patch(target, replacement))
        return self

    def close(self):
        self.patches.close()


def pytest_sessionfinish(session, exitstatus):
    # Called only when this file is explicitly loaded with -p network_guard.
    if ACTIVE.denied:
        session.exitstatus = 1


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"Offline guard: {ACTIVE.denied} nonlocal network attempts")


# The -p plugin is imported before application conftest/modules are collected.
ACTIVE = NetworkGuard().install() if __name__ == "network_guard" else None
