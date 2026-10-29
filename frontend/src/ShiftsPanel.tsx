import { useEffect, useRef, useState, type FormEvent } from 'react';
import './shifts.css';
import { localDateISO } from './dates';

type Break = { start: string; end: string; paid: boolean };
type ShiftDraft = { name: string; start: string; end: string; breaks: Break[]; late_grace_minutes: number; early_grace_minutes: number; capture_before_minutes: number; capture_after_minutes: number };
type Shift = ShiftDraft & { id: string; family_id: string; revision: number; active: boolean; overnight: boolean; timezone: string; expected_work_minutes: number };
type Person = { id: string; code: string; name: string };
type Assignment = { id: string; employee_id: string; employee_code: string; employee_name: string; work_date: string; shift: Shift; cancelled: boolean; cancel_reason: string | null };
type Action = { kind: 'archive'; shift: Shift } | { kind: 'cancel'; row: Assignment };
const defaultDraft = (): ShiftDraft => ({ name: '', start: '08:00', end: '17:00', breaks: [{ start: '12:00', end: '13:00', paid: false }], late_grace_minutes: 0, early_grace_minutes: 0, capture_before_minutes: 120, capture_after_minutes: 120 });
const weekdays = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ nhật'];
const today = () => localDateISO();

export function ShiftsPanel({ csrf, onUnauthorized }: { csrf: string; onUnauthorized: () => void }) {
  const [tab, setTab] = useState<'shifts' | 'assignments'>('shifts');
  const [shifts, setShifts] = useState<Shift[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [shiftId, setShiftId] = useState('');
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [days, setDays] = useState<Set<number>>(new Set([0, 1, 2, 3, 4, 5, 6]));
  const [includeArchived, setIncludeArchived] = useState(false);
  const [includeCancelled, setIncludeCancelled] = useState(false);
  const [rows, setRows] = useState<Assignment[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [editing, setEditing] = useState<Shift | 'new' | null>(null);
  const [draft, setDraft] = useState<ShiftDraft>(defaultDraft);
  const [action, setAction] = useState<Action | null>(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [refresh, setRefresh] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const modal = !!editing || !!action;

  async function request(url: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers); headers.set('X-CSRF-Token', csrf);
    const response = await fetch(url, { ...options, headers, signal: options.signal || AbortSignal.timeout(30000) });
    let body;
    try { body = await response.json(); } catch { throw new Error('Chưa nhận được phản hồi từ máy chủ local.'); }
    if (response.status === 401) onUnauthorized();
    if (!response.ok) {
      const message = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail[0]?.msg : null;
      throw new Error(message?.replace(/^Value error, /, '') || 'Dữ liệu chưa hợp lệ. Kiểm tra và thử lại.');
    }
    return body;
  }

  useEffect(() => {
    const controller = new AbortController();
    request(`/api/admin/shifts?include_archived=${includeArchived}`, { signal: controller.signal }).then(body => {
      if (controller.signal.aborted) return;
      setShifts(body.items);
      setShiftId(previous => body.items.some((item: Shift) => item.id === previous && item.active) ? previous : body.items.find((item: Shift) => item.active)?.id || '');
    }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [refresh, includeArchived]);

  useEffect(() => {
    if (tab !== 'assignments') return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ active: 'true', limit: '100', q: search });
      request('/api/admin/employees?' + params, { signal: controller.signal }).then(body => { if (!controller.signal.aborted) setPeople(body.items); }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [tab, search, refresh]);

  useEffect(() => {
    if (tab !== 'assignments' || !from || !to) return;
    const controller = new AbortController();
    setLoading(true);
    const params = new URLSearchParams({ date_from: from, date_to: to, offset: String(page * 100), limit: '100', include_cancelled: String(includeCancelled) });
    request('/api/admin/shift-assignments?' + params, { signal: controller.signal }).then(body => {
      if (!controller.signal.aborted) { setRows(body.items); setHasMore(body.has_more); }
    }).catch(e => { if (!controller.signal.aborted) { setError(e.message); setRows([]); setHasMore(false); } }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [tab, from, to, page, includeCancelled, refresh]);

  useEffect(() => {
    if (modal && dialog.current && !dialog.current.open) dialog.current.showModal();
    if (!modal) dialog.current?.close();
  }, [modal]);

  function openEditor(shift: Shift | 'new') {
    setError(''); setSuccess(''); setAction(null); setEditing(shift);
    setDraft(shift === 'new' ? defaultDraft() : { name: shift.name, start: shift.start, end: shift.end, breaks: shift.breaks.map(item => ({ ...item })), late_grace_minutes: shift.late_grace_minutes, early_grace_minutes: shift.early_grace_minutes, capture_before_minutes: shift.capture_before_minutes, capture_after_minutes: shift.capture_after_minutes });
  }
  function openAction(next: Action) { setError(''); setSuccess(''); setEditing(null); setReason(''); setAction(next); }
  function closeDialog() { setEditing(null); setAction(null); setError(''); }

  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setSuccess('');
    try {
      if (editing) {
        await request(editing === 'new' ? '/api/admin/shifts' : `/api/admin/shifts/${editing.id}/revisions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(draft) });
        setSuccess(editing === 'new' ? 'Đã tạo ca làm.' : 'Đã tạo phiên bản mới. Các lịch cũ giữ nguyên ca đã phân.');
      } else if (action) {
        const endpoint = action.kind === 'archive' ? `/api/admin/shifts/${action.shift.id}/archive` : `/api/admin/shift-assignments/${action.row.id}/cancel`;
        await request(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason }) });
        setSuccess(action.kind === 'archive' ? 'Đã ngừng dùng ca cho lịch mới. Các lịch đã phân được giữ lại.' : 'Đã hủy lịch; lịch sử và lý do vẫn được giữ lại.');
      }
      closeDialog(); setRefresh(value => value + 1);
    } catch (e) { setError(e instanceof Error ? e.message : 'Không lưu được thay đổi.'); }
    finally { setBusy(false); }
  }

  async function assign(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setSuccess('');
    try {
      const body = await request('/api/admin/shift-assignments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ shift_id: shiftId, employee_ids: [...selected], date_from: from, date_to: to, weekdays: [...days].sort() }) });
      setSuccess(`Đã tạo ${body.created_count} lịch phân ca.`); setPage(0); setRefresh(value => value + 1);
    } catch (e) { setError(e instanceof Error ? e.message : 'Chưa phân được ca.'); }
    finally { setBusy(false); }
  }
  function togglePerson(id: string) {
    setSelected(previous => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id); else if (next.size < 100) next.add(id);
      return next;
    });
  }
  function selectVisible() {
    const next = new Set([...selected, ...people.map(person => person.id)]);
    if (next.size > 100) { setError('Mỗi lần phân tối đa 100 người. Bỏ bớt lựa chọn trước khi chọn thêm.'); return; }
    setSelected(next);
  }

  return <section className="shifts-panel">
    <div className="schedule-heading"><div className="schedule-tabs" aria-label="Ca và lịch"><button className={tab === 'shifts' ? 'selected' : ''} onClick={() => setTab('shifts')}>Ca làm</button><button className={tab === 'assignments' ? 'selected' : ''} onClick={() => setTab('assignments')}>Lịch phân ca</button></div><button onClick={() => openEditor('new')} disabled={busy}>Tạo ca làm</button></div>
    {!modal && error && <p className="error" role="alert">{error}</p>}
    {success && <p className="success" role="status">{success}</p>}
    {tab === 'shifts' ? <>
      <p className="section-explanation">Mỗi lần sửa sẽ tạo phiên bản ca mới. Lịch đã phân tiếp tục dùng giờ và quy tắc của phiên bản cũ. Ca qua đêm thuộc ngày bắt đầu ca.</p>
      <label className="checkbox-label"><input type="checkbox" checked={includeArchived} onChange={event => setIncludeArchived(event.target.checked)} />Hiện cả phiên bản đã ngừng dùng</label>
      <div className="employee-table"><table><thead><tr><th>Ca làm</th><th>Giờ vào – ra</th><th>Nghỉ</th><th>Phút công dự kiến</th><th>Thao tác</th></tr></thead><tbody>{shifts.map(shift => <tr key={shift.id}><td>{shift.name}<br /><small>Phiên bản {shift.revision} · {shift.active ? 'Đang dùng' : 'Đã ngừng'}</small></td><td>{shift.start} – {shift.end}{shift.overnight && ' (+1 ngày)'}</td><td>{shift.breaks.length ? shift.breaks.map((item, index) => <div key={index}>{item.start}–{item.end} · {item.paid ? 'có tính công' : 'không tính công'}</div>) : 'Không có'}</td><td>{shift.expected_work_minutes} phút</td><td>{shift.active && <><button className="text-button" onClick={() => openEditor(shift)} disabled={busy}>Tạo phiên bản mới</button><button className="text-button danger" onClick={() => openAction({ kind: 'archive', shift })} disabled={busy}>Ngừng dùng</button></>}</td></tr>)}{!shifts.length && <tr><td colSpan={5} className="empty-state">Chưa có ca làm. Tạo ca trước khi phân lịch.</td></tr>}</tbody></table></div>
    </> : <>
      <div className="schedule-dates"><label>Từ ngày<input type="date" value={from} onChange={event => { setFrom(event.target.value); setPage(0); }} required /></label><label>Đến ngày<input type="date" value={to} onChange={event => { setTo(event.target.value); setPage(0); }} required /></label><label className="checkbox-label"><input type="checkbox" checked={includeCancelled} onChange={event => { setIncludeCancelled(event.target.checked); setPage(0); }} />Hiện lịch đã hủy</label></div>
      <form className="assignment-form" onSubmit={assign}>
        <fieldset disabled={busy} className="schedule-form-fields">
        <h3>Phân ca hàng loạt</h3><p className="section-explanation">Mỗi lần chọn tối đa 100 người trong 31 ngày. Lịch chồng ca sẽ bị từ chối cho cả lượt phân; không tạo dở một phần.</p>
        <label>Ca áp dụng<select value={shiftId} onChange={event => setShiftId(event.target.value)} required><option value="">Chọn ca</option>{shifts.filter(shift => shift.active).map(shift => <option key={shift.id} value={shift.id}>{shift.name} · v{shift.revision} · {shift.start}–{shift.end}</option>)}</select></label>
        <fieldset><legend>Các thứ được phân</legend><div className="weekday-choices">{weekdays.map((day, index) => <label className="checkbox-label" key={day}><input type="checkbox" checked={days.has(index)} onChange={() => setDays(previous => { const next = new Set(previous); if (next.has(index)) next.delete(index); else next.add(index); return next; })} />{day}</label>)}</div></fieldset>
        <label>Tìm nhân viên<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Mã hoặc họ tên" /></label>
        <div className="people-selection-heading"><span>Đã chọn {selected.size}/100 người</span><button type="button" className="text-button" onClick={selectVisible}>Chọn thêm hồ sơ đang hiển thị</button><button type="button" className="text-button" onClick={() => setSelected(new Set())}>Bỏ chọn tất cả</button></div>
        <div className="schedule-people">{people.map(person => <label className="checkbox-label" key={person.id}><input type="checkbox" checked={selected.has(person.id)} onChange={() => togglePerson(person.id)} disabled={!selected.has(person.id) && selected.size >= 100} />{person.code} · {person.name}</label>)}{!people.length && <p>Chưa có hồ sơ đang hoạt động phù hợp.</p>}</div>
        <p className="import-hint">Hiển thị tối đa 100 hồ sơ khớp tìm kiếm. Chỉ các ô đã đánh dấu được phân ca; lựa chọn vẫn được giữ khi đổi từ khóa tìm kiếm.</p>
        <button disabled={busy || !selected.size || !days.size || !shiftId || !from || !to}>{busy ? 'Đang phân ca…' : 'Phân ca cho người đã chọn'}</button>
        </fieldset>
      </form>
      <h3>Lịch đã phân</h3><div className="employee-table" aria-busy={loading}><table><thead><tr><th>Ngày bắt đầu ca</th><th>Nhân viên</th><th>Ca và giờ</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{row.work_date}</td><td>{row.employee_code} · {row.employee_name}</td><td>{row.shift.name} · v{row.shift.revision}<br />{row.shift.start}–{row.shift.end}{row.shift.overnight && ' (+1 ngày)'}</td><td>{row.cancelled ? `Đã hủy · ${row.cancel_reason}` : 'Đang áp dụng'}</td><td>{!row.cancelled && <button className="text-button danger" onClick={() => openAction({ kind: 'cancel', row })} disabled={busy}>Hủy lịch</button>}</td></tr>)}{!rows.length && <tr><td colSpan={5} className="empty-state">{loading ? 'Đang tải lịch…' : 'Chưa có lịch trong khoảng ngày này.'}</td></tr>}</tbody></table></div>
      <div className="pagination"><span>Trang {page + 1}</span><div><button className="text-button" onClick={() => setPage(value => value - 1)} disabled={!page || loading}>Trang trước</button><button className="text-button" onClick={() => setPage(value => value + 1)} disabled={!hasMore || loading}>Trang sau</button></div></div>
    </>}
    <dialog ref={dialog} onCancel={event => { if (busy) event.preventDefault(); else closeDialog(); }}><form onSubmit={save}>
      <div className="dialog-heading"><h2>{editing ? editing === 'new' ? 'Tạo ca làm' : 'Phiên bản ca mới' : action?.kind === 'archive' ? 'Ngừng dùng ca' : 'Hủy lịch phân ca'}</h2><button type="button" className="text-button" onClick={closeDialog} disabled={busy}>Đóng</button></div>
      <fieldset disabled={busy} className="schedule-form-fields">
      {editing ? <>
        <label>Tên ca<input value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} minLength={2} maxLength={100} required /></label>
        <div className="shift-time-row"><label>Giờ vào<input type="time" value={draft.start} onChange={event => setDraft({ ...draft, start: event.target.value })} required /></label><label>Giờ ra<input type="time" value={draft.end} onChange={event => setDraft({ ...draft, end: event.target.value })} required /></label></div>
        <p className="section-explanation">Giờ ra sớm hơn giờ vào là ca qua đêm. Ngày phân ca là ngày bắt đầu.</p>
        <fieldset><legend>Khoảng nghỉ</legend>{draft.breaks.map((item, index) => <div className="shift-break-row" key={index}><label>Từ<input type="time" value={item.start} onChange={event => setDraft({ ...draft, breaks: draft.breaks.map((value, i) => i === index ? { ...value, start: event.target.value } : value) })} required /></label><label>Đến<input type="time" value={item.end} onChange={event => setDraft({ ...draft, breaks: draft.breaks.map((value, i) => i === index ? { ...value, end: event.target.value } : value) })} required /></label><label className="checkbox-label"><input type="checkbox" checked={item.paid} onChange={event => setDraft({ ...draft, breaks: draft.breaks.map((value, i) => i === index ? { ...value, paid: event.target.checked } : value) })} />Tính công</label><button type="button" className="text-button danger" onClick={() => setDraft({ ...draft, breaks: draft.breaks.filter((_, i) => i !== index) })}>Bỏ</button></div>)}<button type="button" className="text-button" onClick={() => setDraft({ ...draft, breaks: [...draft.breaks, { start: '12:00', end: '13:00', paid: false }] })} disabled={draft.breaks.length >= 8}>Thêm khoảng nghỉ</button></fieldset>
        <div className="shift-time-row"><label>Dung sai đi muộn (phút)<input type="number" min={0} max={180} value={draft.late_grace_minutes} onChange={event => setDraft({ ...draft, late_grace_minutes: Number(event.target.value) })} required /></label><label>Dung sai về sớm (phút)<input type="number" min={0} max={180} value={draft.early_grace_minutes} onChange={event => setDraft({ ...draft, early_grace_minutes: Number(event.target.value) })} required /></label></div>
        <div className="shift-time-row"><label>Cửa sổ quét trước ca (phút)<input type="number" min={0} max={720} value={draft.capture_before_minutes} onChange={event => setDraft({ ...draft, capture_before_minutes: Number(event.target.value) })} required /></label><label>Cửa sổ quét sau ca (phút)<input type="number" min={0} max={720} value={draft.capture_after_minutes} onChange={event => setDraft({ ...draft, capture_after_minutes: Number(event.target.value) })} required /></label></div>
        <p className="import-hint">Cửa sổ quét giúp tìm sự kiện thuộc ca, không tự cộng thêm phút công. Các giờ mẫu trên form cần được sửa theo lịch thực tế của đơn vị.</p>
      </> : <><p className="section-explanation">{action?.kind === 'archive' ? `${action.shift.name}: các lịch đã phân giữ nguyên phiên bản này, chỉ chặn phân ca mới.` : action ? `${action.row.employee_code} · ${action.row.work_date} · ${action.row.shift.name}. Lịch sử hủy được giữ lại.` : ''}</p><label>Lý do<input value={reason} onChange={event => setReason(event.target.value)} minLength={5} maxLength={500} required /></label></>}
      {error && <p className="error" role="alert">{error}</p>}
      <button disabled={busy}>{busy ? 'Đang lưu…' : editing ? 'Lưu ca làm' : 'Lưu thay đổi'}</button>
      </fieldset>
    </form></dialog>
  </section>;
}
