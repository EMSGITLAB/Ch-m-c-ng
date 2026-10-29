import { useEffect, useRef, useState, type FormEvent } from 'react';
import { localDateISO } from './dates';
import './timesheets.css';

type Person = { id: string; code: string; name: string };
type EventInfo = { id: string; direction: string; at: string; source?: string };
type ExceptionEvent = { event_id: string; employee_code: string; employee_name: string; at: string; direction: string; candidate_assignments?: string[] };
type SheetRow = {
  assignment_id: string; employee_code: string; employee_name: string; work_date: string; timezone: string;
  shift: { name: string; revision: number; start: string; end: string; overnight: boolean };
  status: string; exceptions: string[]; first_in: string | null; last_out: string | null;
  worked_seconds: number | null; confirmed_seconds: number; expected_seconds: number; presence_seconds: number;
  unpaid_break_seconds: number; paid_break_credit_seconds: number; outside_shift_seconds: number;
  late_seconds: number | null; early_seconds: number | null; is_late: boolean; is_early: boolean; events: EventInfo[];
};
type Report = {
  functional_trial_event_count?: number;
  source_digest: string;
  finalized: boolean; snapshot_revision?: number; snapshot_reason?: string; is_current?: boolean; employee_catalog?: Record<string, {code: string; name: string}>;
  as_of: string; calculation_version: string; rows: SheetRow[]; offset: number; limit: number; has_more: boolean;
  summary: { row_count: number; status_counts: Record<string, number>; worked_seconds: number; late_count: number; early_count: number; unassigned_count: number; ambiguous_count: number };
  period: { date_from: string; date_to: string; timezone: string; employee_name: string | null };
  unassigned_events: ExceptionEvent[]; ambiguous_events: ExceptionEvent[]; exception_lists_truncated: boolean;
};
const statuses: Record<string, string> = { complete: 'Đã ghép đủ', incomplete: 'Thiếu dữ liệu', needs_review: 'Cần xem lại', pending: 'Đang chờ lượt', in_progress: 'Đang trong ca', upcoming: 'Chưa bắt đầu' };
const exceptions: Record<string, string> = { missing_in: 'Thiếu lượt vào', missing_out: 'Thiếu lượt ra', repeated_in: 'Vào liên tiếp không có lượt ra', same_time_conflict: 'Vào/ra trùng thời điểm', ambiguous_window: 'Chưa xác định duy nhất ca', no_punches: 'Chưa có lượt vào/ra', invalid_pair_order: 'Thứ tự vào/ra chưa hợp lệ' };
const minutes = (seconds: number | null) => seconds === null ? '—' : seconds > 0 && seconds < .6 ? '<0,01' : (seconds / 60).toLocaleString('vi-VN', { maximumFractionDigits: 2 });
function timestamp(value: string | null, timezone: string) {
  return value ? new Intl.DateTimeFormat('vi-VN', { timeZone: timezone, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(value)) : '—';
}

export function TimesheetsPanel({ csrf, onUnauthorized, range, frozen }: { csrf: string; onUnauthorized: () => void; range?: {from: string; to: string}; frozen?: {month: string; revision: number} }) {
  const [from, setFrom] = useState(() => range?.from || localDateISO().slice(0, 8) + '01');
  const [to, setTo] = useState(() => range?.to || localDateISO());
  const [search, setSearch] = useState('');
  const [people, setPeople] = useState<Person[]>([]);
  const [person, setPerson] = useState<Person | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const pending = useRef<AbortController | null>(null);
  const currentRequest = useRef(0);

  useEffect(() => {
    if (frozen) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch('/api/admin/employees?' + new URLSearchParams({ q: search, limit: '100' }), { signal: controller.signal });
        if (response.status === 401) onUnauthorized();
        if (!response.ok) throw new Error('Không tải được danh sách nhân viên.');
        const body = await response.json();
        if (!controller.signal.aborted) setPeople(body.items);
      } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Chưa kết nối được máy chủ.'); }
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [search]);
  useEffect(() => { void load(0); return () => { currentRequest.current++; pending.current?.abort(); }; }, []);

  function changed() { currentRequest.current++; pending.current?.abort(); setBusy(false); setReport(null); setError(''); setExpanded(null); }
  async function load(page: number) {
    if (!from || !to) return;
    pending.current?.abort();
    const controller = new AbortController(); pending.current = controller;
    const sequence = ++currentRequest.current;
    const deadline = setTimeout(() => controller.abort(), 30000);
    setBusy(true); setError(''); setExpanded(null);
    try {
      const params = new URLSearchParams({ date_from: from, date_to: to, offset: String(page * 100), limit: '100' });
      if (person) params.set('employee_id', person.id);
      let endpoint = '/api/admin/timesheets/preview';
      if (frozen) { endpoint = `/api/admin/timesheets/periods/${frozen.month}/snapshot`; params.set('revision', String(frozen.revision)); params.delete('date_from'); params.delete('date_to'); }
      const response = await fetch(endpoint + '?' + params, { headers: { 'X-CSRF-Token': csrf }, signal: controller.signal });
      let body;
      try { body = await response.json(); } catch { throw new Error('Chưa nhận được kết quả từ máy chủ local.'); }
      if (response.status === 401) onUnauthorized();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Bộ lọc chưa hợp lệ. Mỗi lần tra tối đa 31 ngày.');
      if (sequence === currentRequest.current) { setReport(body); if (frozen) setPeople(Object.entries(body.employee_catalog as Record<string, {code:string; name:string}>).map(([id, value]) => ({id, ...value}))); }
    } catch (e) {
      if (sequence === currentRequest.current) { setReport(null); setError(controller.signal.aborted ? 'Chưa tính xong trong thời gian chờ. Hãy thu hẹp bộ lọc và thử lại.' : e instanceof Error ? e.message : 'Không tính được bảng công.'); }
    } finally { clearTimeout(deadline); if (sequence === currentRequest.current) setBusy(false); }
  }
  function submit(event: FormEvent) { event.preventDefault(); void load(0); }
  async function download(format: 'csv' | 'xlsx') {
    if (!report) return;
    setExporting(true); setError('');
    try {
      const params = new URLSearchParams({ format, source: frozen ? 'snapshot' : 'preview', source_digest: report.source_digest });
      if (person) params.set('employee_id', person.id);
      if (frozen) { params.set('month', frozen.month); params.set('revision', String(frozen.revision)); }
      else { params.set('date_from', report.period.date_from); params.set('date_to', report.period.date_to); params.set('as_of', report.as_of); }
      const response = await fetch('/api/admin/timesheets/export?' + params, { signal: AbortSignal.timeout(60000) });
      if (response.status === 401) onUnauthorized();
      if (!response.ok) { const body = await response.json(); throw new Error(typeof body.detail === 'string' ? body.detail : 'Chưa xuất được báo cáo.'); }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob), link = document.createElement('a');
      link.href = url; link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || `bang-cong.${format}`;
      document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (error) { setError(error instanceof Error ? error.message : 'Chưa xuất được báo cáo.'); }
    finally { setExporting(false); }
  }
  const sourcePeople = people;
  const choices = person && !sourcePeople.some(item => item.id === person.id) ? [person, ...sourcePeople] : sourcePeople;
  const counts = report?.summary.status_counts || {};
  return <section className="timesheets-panel">
    <p className="section-explanation">{frozen ? 'Bản chốt được đọc từ dữ liệu đã lưu tại thời điểm khóa kỳ, bao gồm tên hồ sơ và quy tắc ca khi đó.' : 'Bảng xem trước ghép các lượt vào/ra theo lịch ca và áp dụng các điều chỉnh còn hiệu lực.'} Ca thiếu hoặc mơ hồ chưa được cộng vào tổng phút đã xác định. Giờ ngoài ca được báo riêng, chưa tự tính tăng ca.</p>
    <form className="timesheet-filters" onSubmit={submit}>
      <label>Từ ngày<input type="date" value={from} onChange={event => { changed(); setFrom(event.target.value); }} required readOnly={!!range} /></label>
      <label>Đến ngày<input type="date" value={to} onChange={event => { changed(); setTo(event.target.value); }} required readOnly={!!range} /></label>
      {!frozen && <label>Tìm hồ sơ để chọn<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Mã hoặc họ tên" /></label>}
      <label>Nhân viên<select value={person?.id || ''} onChange={event => { changed(); setPerson(choices.find(item => item.id === event.target.value) || null); }}><option value="">Tất cả nhân viên</option>{choices.map(item => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
      <button disabled={busy}>{busy ? 'Đang tải…' : frozen ? 'Tải bản chốt theo bộ lọc' : 'Tính lại bảng công'}</button>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {busy && <p role="status" className="section-explanation">Đang đọc sự kiện và tính theo phiên bản ca đã phân…</p>}
    {report && <>
      {!!report.functional_trial_event_count && <p className="timesheet-snapshot-notice">Báo cáo có {report.functional_trial_event_count} lượt từ chế độ thử chức năng local.</p>}
      <div className="time-actions"><button className="text-button" onClick={() => void download('csv')} disabled={busy || exporting}>{exporting ? 'Đang xuất…' : 'Xuất CSV'}</button><button className="text-button" onClick={() => void download('xlsx')} disabled={busy || exporting}>Xuất Excel (.xlsx)</button><span className="import-hint">Xuất toàn bộ kết quả theo bộ lọc, gồm lượt ngoại lệ. Excel giữ mã nhân viên có số 0 đầu.</span></div>
      {report.finalized && <p className="timesheet-snapshot-notice">Bản chốt v{report.snapshot_revision} · {report.is_current ? 'Đang có hiệu lực' : 'Bản lưu đối chiếu, kỳ đã mở lại hoặc có phiên bản mới'}. Lý do chốt: {report.snapshot_reason}</p>}
      <div className="timesheet-summary"><div><span>Phút trong ca đã xác định</span><strong>{minutes(report.summary.worked_seconds)}</strong><small>Từ {counts.complete || 0} ca đã ghép đủ</small></div><div><span>Ca thiếu dữ liệu / cần xem lại</span><strong>{(counts.incomplete || 0) + (counts.needs_review || 0) + (counts.pending || 0)}</strong><small>{counts.in_progress || 0} ca đang diễn ra · {counts.upcoming || 0} ca chưa bắt đầu</small></div><div><span>Lượt chưa gắn ca / mơ hồ</span><strong>{report.summary.unassigned_count} / {report.summary.ambiguous_count}</strong><small>Cần xem lịch hoặc bổ sung dữ liệu</small></div></div>
      <p className="timesheet-scope">{report.period.date_from} → {report.period.date_to} · {report.period.employee_name || 'Tất cả nhân viên'} · Tính lúc {timestamp(report.as_of, report.period.timezone)}</p>
      <div className="employee-table"><table><thead><tr><th>Ngày / ca</th><th>Nhân viên</th><th>Vào đầu / ra cuối</th><th>Phút trong ca</th><th>Muộn / sớm (phút)</th><th>Trạng thái</th><th>Chi tiết</th></tr></thead><tbody>{report.rows.map(row => <TimesheetRow key={row.assignment_id} row={row} expanded={expanded === row.assignment_id} onToggle={() => setExpanded(value => value === row.assignment_id ? null : row.assignment_id)} />)}{!report.rows.length && <tr><td colSpan={7} className="empty-state">Chưa có lịch ca trong khoảng ngày đã chọn. Lượt chưa có ca được liệt kê riêng bên dưới.</td></tr>}</tbody></table></div>
      <div className="pagination"><span>{report.summary.row_count} ca · Trang {report.offset / report.limit + 1}</span><div><button className="text-button" disabled={busy || !report.offset} onClick={() => void load(report.offset / report.limit - 1)}>Trang trước</button><button className="text-button" disabled={busy || !report.has_more} onClick={() => void load(report.offset / report.limit + 1)}>Trang sau</button></div></div>
      {(report.unassigned_events.length > 0 || report.ambiguous_events.length > 0) && <details className="timesheet-exceptions"><summary>Xem lượt chưa gắn ca hoặc chưa xác định duy nhất ca</summary><div className="employee-table"><table><thead><tr><th>Nhân viên</th><th>Thời điểm</th><th>Chiều</th><th>Vấn đề</th></tr></thead><tbody>{[...report.unassigned_events.map(item => ({ ...item, issue: 'Chưa có ca phù hợp' })), ...report.ambiguous_events.map(item => ({ ...item, issue: `Khớp ${item.candidate_assignments?.length || 0} ca, cần xem lại` }))].map(item => <tr key={item.event_id}><td>{item.employee_code} · {item.employee_name}</td><td>{timestamp(item.at, report.period.timezone)}</td><td>{item.direction === 'in' ? 'Vào' : 'Ra'}</td><td>{item.issue}</td></tr>)}</tbody></table></div>{report.exception_lists_truncated && <p>Chỉ hiển thị 300 lượt đầu mỗi nhóm. Thu hẹp ngày hoặc nhân viên để xem thêm.</p>}</details>}
      <p className="import-hint">{frozen ? 'Đang xem bản chốt đã lưu.' : 'Đây là bản xem trước, chưa phải bản chốt kỳ.'} Phút được hiển thị rút gọn; phép tính giữ thời gian thực đến phần giây. Dung sai chỉ phân loại muộn/sớm, không bù thêm phút công.</p>
    </>}
  </section>;
}

function TimesheetRow({ row, expanded, onToggle }: { row: SheetRow; expanded: boolean; onToggle: () => void }) {
  return <>
    <tr><td>{row.work_date}<br /><small>{row.shift.name} · v{row.shift.revision} · {row.shift.start}–{row.shift.end}{row.shift.overnight && ' (+1 ngày)'}</small></td><td>{row.employee_code} · {row.employee_name}</td><td>{timestamp(row.first_in, row.timezone)}<br />{timestamp(row.last_out, row.timezone)}</td><td>{row.worked_seconds === null ? 'Chưa xác định' : `${minutes(row.worked_seconds)} phút`}<br /><small>Dự kiến {minutes(row.expected_seconds)} phút</small></td><td><span className={row.is_late ? 'timesheet-alert' : ''}>{minutes(row.late_seconds)}</span> / <span className={row.is_early ? 'timesheet-alert' : ''}>{minutes(row.early_seconds)}</span></td><td><span className={`timesheet-status status-${row.status}`}>{statuses[row.status] || row.status}</span></td><td><button className="text-button" onClick={onToggle} aria-expanded={expanded}>{expanded ? 'Thu gọn' : 'Xem lượt'}</button></td></tr>
    {expanded && <tr className="timesheet-detail"><td colSpan={7}><div className="timesheet-detail-grid"><div><strong>Các lượt được gắn vào ca</strong>{row.events.length ? <ul>{row.events.map(event => <li key={event.id}>{event.direction === 'in' ? 'Vào' : 'Ra'} · {timestamp(event.at, row.timezone)}{event.source === 'manual' && ' · Bổ sung bởi quản trị'}</li>)}</ul> : <p>Chưa có lượt gắn được duy nhất vào ca này.</p>}</div><div><strong>Cách tính</strong><p>Phút đã ghép được: {minutes(row.confirmed_seconds)}<br />Nghỉ không công đã trừ: {minutes(row.unpaid_break_seconds)}<br />Nghỉ có công bù khoảng vắng: {minutes(row.paid_break_credit_seconds)}<br />Ngoài ca, chưa tự tính tăng ca: {minutes(row.outside_shift_seconds)}</p>{row.exceptions.length > 0 && <ul className="timesheet-alert">{row.exceptions.map(code => <li key={code}>{exceptions[code] || code}</li>)}</ul>}</div></div></td></tr>}
  </>;
}
