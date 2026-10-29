import json
import socket

import pytest
from app.runtime_supervisor import AlreadyRunning, FileLease, Supervisor, request_stop, service_status


def test_runtime_lease_is_exclusive_and_released_without_trusting_stale_pid(tmp_path):
    lease = FileLease(tmp_path / "service.lock")
    (tmp_path / "service-state.json").write_text(json.dumps({"supervisor_pid": 1, "instance_nonce": "test"}))
    try:
        assert service_status(tmp_path)["running"] is True
        with pytest.raises(AlreadyRunning):
            FileLease(tmp_path / "service.lock")
    finally:
        lease.close()
    assert service_status(tmp_path)["running"] is False
    assert request_stop(tmp_path) is True


def test_stop_control_is_bound_to_current_instance_not_pid(tmp_path):
    supervisor = Supervisor(tmp_path, tmp_path / "runtime")
    path = tmp_path / "runtime/service-stop.json"
    path.write_text(json.dumps({"instance_nonce": "stale"}))
    assert supervisor.stopping() is False
    path.write_text(json.dumps({"instance_nonce": supervisor.instance}))
    assert supervisor.stopping() is True
    for handler in supervisor.logger.handlers:
        handler.close()


def test_occupied_port_is_not_adopted_or_terminated(tmp_path):
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        supervisor = Supervisor(tmp_path, tmp_path / "runtime", other.getsockname()[1])
        assert supervisor.run() == 3
        assert service_status(tmp_path / "runtime")["running"] is False
        assert other.fileno() >= 0
