"""Reconciliation math, immutable evidence and correction/close races."""

import csv
import io
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from app import partner_attendance as attendance
from app import partner_reports as reports
from app.models import (
    PartnerBatch,
    PartnerEvent,
    PartnerReportAdjustment,
    PartnerReportSnapshot,
    PartnerVendor,
)
from app.partner_retention import expire_partner_faces
from fastapi import HTTPException
from sqlalchemy import func, select
from test_partner_admin import partner_setup as partner_setup
from test_partner_attendance import partner_kiosk as partner_kiosk

ROOT = "/api/admin/partners"


def report(k):
    response = k["browser"].get(ROOT+f"/batches/{k['batch_id']}/report")
    assert response.status_code == 200, response.text
    return response.json()


def review(k):
    response = k["browser"].post(ROOT+f"/batches/{k['batch_id']}/state", headers=k["headers"],
        json={"state":"review","expected_state":"open","reason":"Kiểm tra đối soát ca thử"})
    assert response.status_code == 200, response.text


def amendment(k, worker, source, **changes):
    return {"request_id":str(uuid4()), "expected_source":source, "reason":"Bổ sung theo xác nhận tại sàn", **changes}


def amend(k, worker, payload):
    return k["browser"].post(ROOT+f"/workers/{worker['id']}/adjustments", headers=k["headers"], json=payload)


def finish(k, **changes):
    body = {"request_id":str(uuid4()), "expected_source":report(k)["source_hash"], "reason":"Đã kiểm tra đối soát với sàn", **changes}
    response = k["browser"].post(ROOT+f"/batches/{k['batch_id']}/close", headers=k["headers"], json=body)
    return response, body


def test_report_and_corrections_require_admin_and_csrf(client):
    browser, _ = client
    batch, worker = str(uuid4()), str(uuid4())
    assert browser.get(ROOT+f"/batches/{batch}/report").status_code == 401
    assert browser.post(ROOT+f"/workers/{worker}/adjustments", json={}).status_code == 401
    assert browser.post(ROOT+f"/batches/{batch}/close", json={}).status_code == 401


def test_pending_is_not_admitted_and_missing_out_is_not_a_full_shift(partner_kiosk):
    k = partner_kiosk
    k["admitted"]()
    k["capture"]("B")
    result = report(k)
    assert result["summary"]["admitted"] == 1 and result["summary"]["pending"] == 1
    assert result["summary"]["incomplete"] == 1 and result["summary"]["total_worked_seconds"] == 0
    active = next(row for row in result["rows"] if row["admitted"])
    assert active["status"] == "missing_out" and active["worked_seconds"] is None
    assert active["out_at"] is None and active["raw_out_at"] is None
    before = result["source_hash"]
    k["clock"][0] += timedelta(seconds=1)
    assert report(k)["source_hash"] == before
    assert "token_hash" not in str(result) and "face_reference" not in str(result)


def test_work_math_clips_shift_and_deducts_only_overlapping_unpaid_breaks(partner_kiosk):
    k = partner_kiosk
    with k["factory"]() as db:
        batch = db.get(PartnerBatch, k["batch_id"])
        batch.starts_at, batch.ends_at = datetime(2026,10,30,1,tzinfo=UTC), datetime(2026,10,30,10,tzinfo=UTC)
        batch.admission_from, batch.checkout_until = batch.starts_at-timedelta(hours=1), batch.ends_at+timedelta(hours=1)
        batch.rules = {"breaks":[{"start_offset":240,"end_offset":300,"paid":False},{"start_offset":100,"end_offset":110,"paid":True}]}
        from app.models import RecognitionPolicy
        db.get(RecognitionPolicy,batch.policy_id).validated_at = batch.admission_from-timedelta(minutes=1)
        db.commit()
    k["clock"][0] = datetime(2026,10,30,0,50,tzinfo=UTC)
    k["admitted"]()
    with k["factory"]() as db:
        from app.models import Device
        db.get(Device,k["ids"][0]).direction = "out"
        db.commit()
    k["clock"][0] = datetime(2026,10,30,10,10,tzinfo=UTC)
    proof, _ = k["capture"]()
    assert k["commit"](proof).status_code == 200
    row = report(k)["rows"][0]
    assert row["worked_seconds"] == 8*3600 and row["expected_seconds"] == 8*3600
    assert row["unpaid_break_seconds"] == 3600 and row["outside_shift_seconds"] > 1100


def test_partial_break_is_not_subtracted_twice():
    batch=SimpleNamespace(starts_at=datetime(2026,10,30,1,tzinfo=UTC), ends_at=datetime(2026,10,30,10,tzinfo=UTC),
        rules={"breaks":[{"start_offset":240,"end_offset":300,"paid":False}]})
    worker=SimpleNamespace(id="w",code="001",declared_name="Thử",name_source="manual",state="completed",
        biometric_expires_at=datetime(2026,11,1,tzinfo=UTC))
    events=[{"direction":"in","server_time":"2026-10-30T05:30:00+00:00"}, {"direction":"out","server_time":"2026-10-30T06:15:00+00:00"}]
    row=reports.effective_row(batch,worker,events,[],datetime(2026,10,30,7,tzinfo=UTC))
    assert row["elapsed_seconds"] == 45*60 and row["unpaid_break_seconds"] == 30*60 and row["worked_seconds"] == 15*60


def test_local_wall_time_is_interpreted_in_batch_timezone_not_browser_timezone(partner_kiosk):
    k=partner_kiosk
    worker,_=k["admitted"]()
    review(k)
    k["clock"][0] += timedelta(minutes=10)
    from zoneinfo import ZoneInfo
    local=k["clock"][0].astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).replace(tzinfo=None).isoformat()
    current=report(k)
    response=amend(k,worker,amendment(k,worker,current["source_hash"],out_local=local))
    assert response.status_code == 200,response.text
    actual=datetime.fromisoformat(report(k)["rows"][0]["out_at"])
    assert actual == k["clock"][0]


def test_recovery_counts_compatibility_and_guard_preserve_partner_documents(partner_kiosk):
    from app.models import Device, PartnerDeviceBinding, RecognitionPolicy
    from app.native_backup import recovery_counts, recovery_guard
    k=partner_kiosk
    k["admitted"]()
    review(k)
    response,_=finish(k,acknowledge_incomplete=True)
    assert response.status_code == 200
    with k["factory"]() as db:
        current=recovery_counts(db)
        assert current["partner_workers"] == 1 and current["partner_events"] == 1 and current["partner_report_snapshots"] == 1
        legacy={name:current[name] for name in ("employees","face_templates","imported_face_photos","attendance_events")}
        assert recovery_counts(db,legacy) == legacy
        with pytest.raises(ValueError):
            recovery_counts(db,["arbitrary_table"])
        recovery_guard(db,{})
        db.commit()
        assert not db.get(PartnerDeviceBinding,k["ids"][0]).active
        assert all(device.token_hash is None for device in db.scalars(select(Device)))
        assert not any(policy.enabled for policy in db.scalars(select(RecognitionPolicy)))
        assert reports.build_report(db,k["batch_id"]) == response.json()


@pytest.mark.skipif(not os.environ.get("CHAMCONG_TEST_DATABASE_URL"),reason="Native SQL backup/restore, isolated database only")
def test_native_backup_restore_keeps_partner_snapshot_but_never_restores_temporary_faces(partner_kiosk,tmp_path,monkeypatch):
    import re

    import pyodbc
    from app import native_backup
    from app.config import get_settings
    from app.models import Device
    from app.private_storage import recovery_key, unseal
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL
    from sqlalchemy.orm import Session
    k=partner_kiosk
    k["admitted"]()
    review(k)
    response,_=finish(k,acknowledge_incomplete=True)
    assert response.status_code == 200
    expected=response.json()
    name=os.environ['CHAMCONG_TEST_DB_NAME']
    assert re.fullmatch(r'ChamCong_AdminCheck_[0-9a-f]{8}',name)
    with k['factory']() as db:
        assert db.scalar(text('select DB_NAME()')) == name
        db.execute(text("EXEC sys.sp_addextendedproperty @name=N'chamcong_project', @value=N'chamcong-face-local'"))
        db.commit()
    project=tmp_path/'isolated-project'
    project.mkdir()
    (project/'.env').write_text('# Test-only recovery configuration\n',encoding='utf-8')
    for path in native_backup.source_files(project).values():
        if not path.exists():
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('{}' if path.suffix=='.json' else '# Test-only public recovery input\n',encoding='utf-8')
    settings=get_settings()
    runtime=settings.runtime_dir
    assert list((runtime/'partner-biometrics').glob('*.face'))
    monkeypatch.setattr(native_backup,'PROJECT_ROOT',project)
    monkeypatch.setattr(native_backup,'session_factory',lambda:k['factory'])
    metadata=native_backup.create_backup(tmp_path/'encrypted-backup')
    archive=metadata['archive_path']
    content=unseal(Path(archive).read_bytes(),recovery_key(runtime))
    manifest=native_backup.validate_payload(content)
    assert manifest['row_counts']['partner_report_snapshots']==1
    assert not any('partner-biometrics' in name for name in manifest['files'])
    assert expire_partner_faces(runtime,k['clock'][0]+timedelta(days=5))['expired_removed']>0
    target='ChamCong_RecoveryCheck_'+uuid4().hex[:8]
    engine=None
    try:
        recovered=native_backup.restore_new_database(archive,target_name=target)
        restored_root=Path(recovered['app_root'])
        assert not (restored_root/'.runtime/partner-biometrics').exists()
        url=URL.create('mssql+pyodbc',query={'odbc_connect':native_backup.connection_string(target)}).render_as_string(hide_password=False)
        engine=create_engine(url,hide_parameters=True)
        with Session(engine) as db:
            assert reports.build_report(db,k['batch_id'])==expected
            assert db.scalar(select(func.count()).select_from(PartnerEvent))==1
            assert all(row.token_hash is None for row in db.scalars(select(Device)))
    finally:
        if engine:
            engine.dispose()
        with pyodbc.connect(native_backup.connection_string('master'),autocommit=True) as connection:
            cursor=connection.cursor()
            if cursor.execute('SELECT DB_ID(?)',target).fetchval() is not None:
                cursor.execute(f'ALTER DATABASE [{target}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
                cursor.execute(f'DROP DATABASE [{target}]')


def test_manual_correction_is_append_only_idempotent_and_rejects_stale_views(partner_kiosk):
    k=partner_kiosk
    worker, _ = k["admitted"]()
    review(k)
    current = report(k)
    k["clock"][0] += timedelta(hours=1)
    payload = amendment(k,worker,current["source_hash"],out_at=k["clock"][0].isoformat(),name="Tên đã đối soát")
    first = amend(k,worker,payload)
    assert first.status_code == 200,first.text
    assert amend(k,worker,payload).json()["replayed"]
    result = report(k)
    assert result["source_hash"] != current["source_hash"]
    row=result["rows"][0]
    assert row["raw_out_at"] is None and row["out_at"] and row["status"] == "complete"
    assert row["sources"]["out_at"] == "manual_adjustment" and row["name"] == "Tên đã đối soát"
    assert row["adjustments"][0]["reason"] == payload["reason"]
    assert amend(k,worker,amendment(k,worker,current["source_hash"],name="Tên cũ ghi đè")).status_code == 409
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 1
        assert db.scalar(select(func.count()).select_from(PartnerReportAdjustment)) == 1
    changed={**payload,"name":"Yêu cầu khác"}
    assert amend(k,worker,changed).status_code == 409


def test_corrections_reject_future_invalid_window_naive_time_empty_reason_and_pending(partner_kiosk):
    k=partner_kiosk
    worker, _=k["admitted"]()
    _, state=k["capture"]("B")
    pending=state["worker"]
    current=report(k)
    payload=amendment(k,worker,current["source_hash"],name="Tên mới")
    assert amend(k,worker,payload).status_code == 409
    review(k)
    current=report(k)
    for changes in [{"out_at":(k["clock"][0]+timedelta(days=1)).isoformat()}, {"out_at":"2026-10-30T06:00:00"},
        {"out_at":current["rows"][0]["in_at"]}, {"reason":""}, {"name":None}, {"in_at":"2020-01-01T00:00:00Z"}]:
        payload=amendment(k,worker,current["source_hash"],**changes)
        assert amend(k,worker,payload).status_code == 422
    assert amend(k,pending,amendment(k,pending,current["source_hash"],name="Tên phiên chờ")).status_code == 409


def test_close_requires_explicit_ack_of_missing_records_and_preserves_them(partner_kiosk):
    k=partner_kiosk
    worker,_=k["admitted"]()
    review(k)
    failed,_=finish(k)
    assert failed.status_code == 409
    completed,body=finish(k,acknowledge_incomplete=True)
    assert completed.status_code == 200,completed.text
    saved=completed.json()
    assert saved["closed"] and saved["summary"]["incomplete"] == 1
    assert saved["rows"][0]["out_at"] is None and saved["rows"][0]["worked_seconds"] is None
    assert k["browser"].post(ROOT+f"/batches/{k['batch_id']}/close",headers=k["headers"],json=body).json() == saved
    assert amend(k,worker,amendment(k,worker,saved["source_hash"],name="Sau khi chốt")).status_code == 409
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerReportSnapshot)) == 1
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 1


def test_closed_report_and_export_survive_expired_biometrics_and_vendor_rename(partner_kiosk):
    k=partner_kiosk
    k["admitted"]()
    review(k)
    response,_=finish(k,acknowledge_incomplete=True)
    saved=response.json()
    with k["factory"]() as db:
        batch=db.get(PartnerBatch,k["batch_id"])
        db.get(PartnerVendor,batch.partner_id).name="Đơn vị đổi tên sau chốt"
        k["clock"][0]=attendance.aware(batch.ends_at)+timedelta(hours=49)
        db.commit()
    from app.config import get_settings
    assert expire_partner_faces(get_settings().runtime_dir,k["clock"][0])["expired_removed"] > 0
    assert report(k) == saved
    exported=k["browser"].get(ROOT+f"/batches/{k['batch_id']}/export.csv?expected_source={saved['source_hash']}")
    assert exported.status_code == 200 and saved["rows"][0]["code"] in exported.text
    assert "Đơn vị đổi tên sau chốt" not in exported.text


def test_csv_matches_reviewed_source_filter_and_neutralizes_formula_names(partner_kiosk):
    k=partner_kiosk
    worker,_=k["admitted"]()
    review(k)
    before=report(k)
    assert amend(k,worker,amendment(k,worker,before["source_hash"],name="=DANGEROUS()")).status_code == 200
    base=ROOT+f"/batches/{k['batch_id']}/export.csv"
    assert k["browser"].get(base+f"?expected_source={before['source_hash']}").status_code == 409
    current=report(k)
    response=k["browser"].get(base+f"?expected_source={current['source_hash']}")
    assert response.status_code == 200
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[1][5] == "'=DANGEROUS()" and rows[1][12] == ""
    filtered=k["browser"].get(base+f"?expected_source={current['source_hash']}&status=complete")
    assert len(list(csv.reader(io.StringIO(filtered.content.decode('utf-8-sig'))))) == 1


def test_corrupt_snapshot_is_not_silently_rebuilt(partner_kiosk):
    k=partner_kiosk
    k["admitted"]()
    review(k)
    response,_=finish(k,acknowledge_incomplete=True)
    assert response.status_code == 200
    with k["factory"]() as db:
        saved=db.get(PartnerReportSnapshot,k["batch_id"])
        saved.report={**saved.report,"note":"tampered"}
        db.commit()
    assert k["browser"].get(ROOT+f"/batches/{k['batch_id']}/report").status_code == 503


def test_closing_pending_names_marks_unadmitted_without_creating_hours(partner_kiosk):
    k=partner_kiosk
    k["capture"]()
    review(k)
    response,_=finish(k)
    assert response.status_code == 200,response.text
    result=response.json()
    assert result["summary"]["admitted"] == 0 and result["summary"]["pending"] == 0
    assert result["summary"]["unadmitted_at_close"] == 1 and result["summary"]["available_slots"] == 0
    assert result["rows"][0]["status"] == "not_admitted" and result["rows"][0]["worked_seconds"] is None
    with k["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(PartnerEvent)) == 0


def test_functional_trial_scope_survives_into_report_and_csv(partner_kiosk):
    k=partner_kiosk
    k["admitted"]()
    with k["factory"]() as db:
        batch=db.get(PartnerBatch,k["batch_id"])
        batch.rules={**batch.rules,"functional_trial":True}
        db.commit()
    current=report(k)
    assert "không dùng làm chứng từ thanh toán" in current["note"]
    exported=k["browser"].get(ROOT+f"/batches/{k['batch_id']}/export.csv?expected_source={current['source_hash']}")
    rows=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert rows[1][-1] == "Chạy thử chức năng - không dùng thanh toán"


def test_disabled_policy_blocks_new_camera_mutations_but_keeps_old_receipts(partner_kiosk):
    from app.models import RecognitionPolicy
    k=partner_kiosk
    k['actor']()
    assert k["browser"].get('/api/kiosk/partners/context').json()['recording_enabled']
    _, receipt=k["admitted"]()
    with k["factory"]() as db:
        batch=db.get(PartnerBatch,k["batch_id"])
        db.get(RecognitionPolicy,batch.policy_id).enabled=False
        db.commit()
    assert k["browser"].post('/api/kiosk/partners/captures',json={"request_id":str(uuid4())},headers={"X-Kiosk-Intent":"start-partner-capture"}).status_code == 503
    assert not k["browser"].get('/api/kiosk/partners/context').json()['recording_enabled']
    recovered=k["browser"].get('/api/kiosk/partners/captures/'+receipt['request_id'])
    assert recovered.status_code == 200 and recovered.json()['receipt']==receipt
    assert report(k)["summary"]["admitted"] == 1


@pytest.mark.skipif(not os.environ.get("CHAMCONG_TEST_DATABASE_URL"),reason="SQL Server transaction locks")
def test_native_close_and_correction_serialize_against_same_source(partner_kiosk):
    k=partner_kiosk
    worker,_=k["admitted"]()
    review(k)
    current=report(k)
    barrier=Barrier(2)
    def action(index):
        with k["factory"]() as db:
            barrier.wait(timeout=15)
            try:
                if index:
                    reports.adjust(UUID(worker["id"]),reports.AdjustmentInput(**amendment(k,worker,current["source_hash"],name="Đã kiểm tra")),db,SimpleNamespace(id=1))
                else:
                    reports.close(UUID(k["batch_id"]),reports.CloseInput(request_id=uuid4(),expected_source=current["source_hash"],reason="Chốt ca thử đồng thời",acknowledge_incomplete=True),db,SimpleNamespace(id=1))
                return 200
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(action,range(2)))
    assert sorted(results) == [200,409]
