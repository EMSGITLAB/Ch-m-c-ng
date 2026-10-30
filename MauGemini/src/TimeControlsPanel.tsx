import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { localDateISO } from './dates';
import { TimesheetsPanel } from './TimesheetsPanel';
import type { TimekeepingProps } from './TimekeepingPanel';

type Person = { id: string; code: string; name: string };
type Entry = { id: string; employee_id: string; employee_code: string; employee_name: string; direction: string; occurred_at: string; voided?: boolean; kind?: string; reason?: string; revoked_at?: string | null; revoke_reason?: string | null; created_at?: string };
type Page = { items: Entry[]; has_more: boolean };
type Action = { title: string; context: string; endpoint: string; body: Record<string, unknown> };
type Period = { month: string; status: string; revision: number; snapshots: { revision: number; created_at: string; reason: string; summary: { row_count: number; worked_seconds: number } }[] };
const root = '/api/admin/timesheets';

function useApi({ csrf, onUnauthorized }: TimekeepingProps) {
  return useCallback(async (url: string, options: RequestInit = {}) => {
    const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...options.headers }, signal: options.signal || AbortSignal.timeout(45000) });
    if (response.status === 401) onUnauthorized();
    let body;
    try { body = await response.json(); } catch { throw new Error('Chưa nhận được kết quả hợp lệ. Hãy tải lại trạng thái trước khi thử lại.'); }
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Dữ liệu chưa hợp lệ. Kiểm tra ngày, giờ và lý do.');
    return body;
  }, [csrf, onUnauthorized]);
}

function formatTime(at: string, timezone: string) {
  return new Intl.DateTimeFormat('vi-VN', { timeZone: timezone, dateStyle: 'short', timeStyle: 'medium', hour12: false }).format(new Date(at));
}
function errorText(error: unknown) { return error instanceof Error ? error.message : 'Chưa xác nhận được kết quả. Hãy tải lại trước khi thử lại.'; }

function useTimezone() {
  const [timezone, setTimezone] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/system/status', { signal: controller.signal }).then(response => response.ok ? response.json() : Promise.reject(new Error())).then(body => setTimezone(body.timezone)).catch(() => {});
    return () => controller.abort();
  }, []);
  return timezone;
}

function ReasonDialog({ action, busy, error, onCancel, onSubmit }: { action: Action; busy: boolean; error: string; onCancel: () => void; onSubmit: (reason: string) => Promise<void> }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState('');
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} className="time-action-dialog" onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2>{action.title}</h2><p>{action.context}</p>
    {error && <p className="error" role="alert">{error}</p>}
    <form onSubmit={event => { event.preventDefault(); void onSubmit(reason); }}>
      <label>Lý do thao tác<textarea value={reason} onChange={event => setReason(event.target.value)} required minLength={5} maxLength={500} disabled={busy} autoFocus /></label>
      <p className="import-hint">Lịch sử và dữ liệu gốc được giữ để đối chiếu. Nếu phản hồi bị gián đoạn, tải lại trạng thái trước khi thao tác tiếp.</p>
      <div className="time-actions"><button type="button" className="text-button" onClick={onCancel} disabled={busy}>Đóng</button><button disabled={busy || reason.trim().length < 5}>{busy ? 'Đang lưu…' : 'Xác nhận thao tác'}</button></div>
    </form>
  </dialog>;
}

export function AttendanceCorrections(props: TimekeepingProps) {
  const api = useApi(props), timezone = useTimezone();
  const [from, setFrom] = useState(() => localDateISO().slice(0, 8) + '01');
  const [to, setTo] = useState(() => localDateISO());
  const [search, setSearch] = useState('');
  const [people, setPeople] = useState<Person[]>([]);
  const [person, setPerson] = useState<Person | null>(null);
  const [raw, setRaw] = useState<Page | null>(null), [history, setHistory] = useState<Page | null>(null);
  const [rawPage, setRawPage] = useState(0), [historyPage, setHistoryPage] = useState(0);
  const [localTime, setLocalTime] = useState(''), [direction, setDirection] = useState('in'), [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(false);
  const [error, setError] = useState(''), [success, setSuccess] = useState('');
  const [action, setAction] = useState<Action | null>(null);
  const request = useRef<{ key: string; id: string } | null>(null);
  const pending = useRef<AbortController | null>(null), sequence = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => api('/api/admin/employees?' + new URLSearchParams({ q: search, limit: '100' }), { signal: controller.signal }).then(body => { if (!controller.signal.aborted) setPeople(body.items); }).catch(error => { if (!controller.signal.aborted) setError(errorText(error)); }), 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [search, api]);
  useEffect(() => { void load(0, 0); return () => { sequence.current++; pending.current?.abort(); }; }, []);

  function changed() { sequence.current++; pending.current?.abort(); setRaw(null); setHistory(null); setRawPage(0); setHistoryPage(0); setError(''); setSuccess(''); setLoading(false); }
  async function load(rawIndex = rawPage, historyIndex = historyPage) {
    if (!from || !to) return;
    pending.current?.abort();
    const controller = new AbortController(); pending.current = controller;
    const current = ++sequence.current;
    setLoading(true); setError('');
    try {
      const base = { date_from: from, date_to: to, limit: '50', ...(person ? { employee_id: person.id } : {}) };
      const results = await Promise.all([
        api(root + '/adjustments/events?' + new URLSearchParams({ ...base, offset: String(rawIndex * 50) }), { signal: controller.signal }),
        api(root + '/adjustments?' + new URLSearchParams({ ...base, offset: String(historyIndex * 50) }), { signal: controller.signal }),
      ]);
      if (current === sequence.current) { setRaw(results[0]); setHistory(results[1]); setRawPage(rawIndex); setHistoryPage(historyIndex); }
    } catch (error) { if (current === sequence.current && !controller.signal.aborted) { setError(errorText(error)); setRaw(null); setHistory(null); } }
    finally { if (current === sequence.current) setLoading(false); }
  }
  async function add(event: FormEvent) {
    event.preventDefault();
    if (!person || !timezone) return;
    const payload = { employee_id: person.id, kind: 'add', direction, local_time: localTime, reason };
    const key = JSON.stringify(payload);
    if (request.current?.key !== key) request.current = { key, id: crypto.randomUUID() };
    setBusy(true); setError(''); setSuccess('');
    try {
      await api(root + '/adjustments', { method: 'POST', body: JSON.stringify({ ...payload, request_id: request.current.id }) });
      setSuccess('Đã lưu lượt bổ sung và lịch sử điều chỉnh. Dữ liệu chấm công gốc được giữ nguyên.');
      request.current = null; setLocalTime(''); setReason(''); await load(0, 0);
    } catch (error) { setError(errorText(error)); }
    finally { setBusy(false); }
  }
  function selectAction(row: Entry, revoke = false) {
    setError(''); setSuccess('');
    const context = `${row.employee_code} · ${row.employee_name} · ${row.direction === 'in' ? 'Vào' : 'Ra'} · ${formatTime(row.occurred_at, timezone)}`;
    setAction(revoke ? { title: 'Thu hồi điều chỉnh', context, endpoint: `${root}/adjustments/${row.id}/revoke`, body: {} }
      : { title: 'Loại lượt khỏi tính công', context, endpoint: root + '/adjustments', body: { request_id: crypto.randomUUID(), employee_id: row.employee_id, kind: 'void', ...(row.kind === 'add' ? { target_adjustment_id: row.id } : { target_event_id: row.id }) } });
  }
  async function confirm(reason: string) {
    if (!action) return;
    setBusy(true); setError(''); setSuccess('');
    try { await api(action.endpoint, { method: 'POST', body: JSON.stringify({ ...action.body, reason }) }); setAction(null); setSuccess('Đã lưu thao tác và lịch sử đối chiếu.'); await load(); }
    catch (error) { setError(errorText(error)); }
    finally { setBusy(false); }
  }
  const choices = person && !people.some(item => item.id === person.id) ? [person, ...people] : people;
  return <section className="time-controls">
    <p className="section-explanation">Bổ sung lượt thiếu, loại lượt sai hoặc thu hồi điều chỉnh. Mỗi thao tác cần lý do; lượt chấm công gốc được giữ nguyên. Kỳ đã khóa phải mở lại trước khi sửa.</p>
    {error && <p className="error" role="alert">{error}</p>}{success && <p className="success" role="status">{success}</p>}
    <form className="time-filter-grid" onSubmit={event => { event.preventDefault(); void load(0, 0); }}>
      <label>Từ ngày<input type="date" value={from} onChange={event => { changed(); setFrom(event.target.value); }} required disabled={busy} /></label>
      <label>Đến ngày<input type="date" value={to} onChange={event => { changed(); setTo(event.target.value); }} required disabled={busy} /></label>
      <label>Tìm hồ sơ<input type="search" value={search} onChange={event => setSearch(event.target.value)} disabled={busy} /></label>
      <label>Nhân viên điều chỉnh<select value={person?.id || ''} onChange={event => { changed(); setPerson(choices.find(item => item.id === event.target.value) || null); }} disabled={busy}><option value="">Tất cả — chọn người khi bổ sung lượt</option>{choices.map(item => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
      <button disabled={busy || loading}>{loading ? 'Đang tải…' : 'Tải lượt & lịch sử'}</button>
    </form>
    <section className="time-control-card"><h2>Bổ sung lượt thiếu</h2><p className="section-explanation">{person ? `${person.code} · ${person.name}` : 'Chọn nhân viên ở bộ lọc trước khi bổ sung.'} · Giờ nhập theo {timezone || 'đang tải múi giờ máy chủ…'}. Không dùng múi giờ của tablet.</p>
      <form className="time-add-grid" onSubmit={add}>
        <label>Thời điểm cần bổ sung<input type="datetime-local" step="1" value={localTime} onChange={event => setLocalTime(event.target.value)} required disabled={busy} /></label>
        <label>Chiều lượt bổ sung<select value={direction} onChange={event => setDirection(event.target.value)} disabled={busy}><option value="in">Vào</option><option value="out">Ra</option></select></label>
        <label className="time-reason">Lý do bổ sung<textarea value={reason} onChange={event => setReason(event.target.value)} required minLength={5} maxLength={500} disabled={busy} /></label>
        <button disabled={busy || !person || !timezone}>{busy ? 'Đang lưu…' : 'Lưu lượt bổ sung'}</button>
      </form>
    </section>
    <h2>Lượt chấm công gốc</h2><div className="employee-table"><table><thead><tr><th>Nhân viên</th><th>Thời điểm / chiều</th><th>Trạng thái tính công</th><th>Thao tác</th></tr></thead><tbody>{raw?.items.map(row => <tr key={row.id}><td>{row.employee_code} · {row.employee_name}</td><td>{timezone && formatTime(row.occurred_at, timezone)} · {row.direction === 'in' ? 'Vào' : 'Ra'}</td><td>{row.voided ? 'Đã loại bằng điều chỉnh' : 'Đang có hiệu lực'}</td><td><button className="text-button" disabled={busy || row.voided || !timezone} onClick={() => selectAction(row)}>Loại khỏi tính công</button></td></tr>)}{raw && !raw.items.length && <tr><td colSpan={4}>Chưa có lượt gốc trong bộ lọc.</td></tr>}</tbody></table></div>
    <div className="pagination"><span>Trang lượt gốc {rawPage + 1}</span><div><button className="text-button" disabled={busy || loading || !rawPage} onClick={() => void load(rawPage - 1, historyPage)}>Lượt gốc trước</button><button className="text-button" disabled={busy || loading || !raw?.has_more} onClick={() => void load(rawPage + 1, historyPage)}>Lượt gốc tiếp</button></div></div>
    <h2>Lịch sử điều chỉnh</h2><div className="employee-table"><table><thead><tr><th>Nhân viên</th><th>Thời điểm tác động</th><th>Nội dung / lý do</th><th>Hiệu lực / thao tác</th></tr></thead><tbody>{history?.items.map(row => <tr key={row.id}><td>{row.employee_code} · {row.employee_name}</td><td>{timezone && formatTime(row.occurred_at, timezone)}<br />{row.direction === 'in' ? 'Vào' : 'Ra'}</td><td>{row.kind === 'add' ? 'Bổ sung lượt' : 'Loại lượt'}<br /><span className="time-wrap">{row.reason}</span>{row.revoke_reason && <p className="time-wrap">Thu hồi: {row.revoke_reason}</p>}</td><td>{row.revoked_at ? 'Đã thu hồi' : <><button className="text-button" disabled={busy || !timezone} onClick={() => selectAction(row, true)}>Thu hồi điều chỉnh</button>{row.kind === 'add' && <button className="text-button" disabled={busy || !timezone} onClick={() => selectAction(row)}>Loại lượt bổ sung</button>}</>}</td></tr>)}{history && !history.items.length && <tr><td colSpan={4}>Chưa có điều chỉnh trong bộ lọc.</td></tr>}</tbody></table></div>
    <div className="pagination"><span>Trang lịch sử {historyPage + 1}</span><div><button className="text-button" disabled={busy || loading || !historyPage} onClick={() => void load(rawPage, historyPage - 1)}>Lịch sử trước</button><button className="text-button" disabled={busy || loading || !history?.has_more} onClick={() => void load(rawPage, historyPage + 1)}>Lịch sử tiếp</button></div></div>
    {action && <ReasonDialog action={action} busy={busy} error={error} onCancel={() => setAction(null)} onSubmit={confirm} />}
  </section>;
}

export function PeriodControl(props: TimekeepingProps) {
  const api = useApi(props), timezone = useTimezone();
  const [month, setMonth] = useState(() => localDateISO().slice(0, 7));
  const [period, setPeriod] = useState<Period | null>(null), [busy, setBusy] = useState(false), [loading, setLoading] = useState(false);
  const [error, setError] = useState(''), [success, setSuccess] = useState('');
  const [allowUnresolved, setAllowUnresolved] = useState(false);
  const [selected, setSelected] = useState<number | 'preview' | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const sequence = useRef(0), pending = useRef<AbortController | null>(null);
  useEffect(() => { void load(); return () => { sequence.current++; pending.current?.abort(); }; }, []);
  function changed(value: string) { sequence.current++; pending.current?.abort(); setMonth(value); setPeriod(null); setSelected(null); setError(''); setSuccess(''); setLoading(false); setAllowUnresolved(false); }
  async function load() {
    if (!month) return;
    pending.current?.abort(); const controller = new AbortController(); pending.current = controller;
    const current = ++sequence.current; setLoading(true); setError('');
    try { const body = await api(`${root}/periods/${month}`, { signal: controller.signal }); if (current === sequence.current) { setPeriod(body); setSelected(body.snapshots.length ? body.revision : 'preview'); } }
    catch (error) { if (current === sequence.current && !controller.signal.aborted) { setPeriod(null); setError(errorText(error)); } }
    finally { if (current === sequence.current) setLoading(false); }
  }
  function begin() {
    if (!period) return;
    setError(''); setSuccess('');
    const locked = period.status === 'locked';
    setAction({ title: locked ? 'Mở lại kỳ công' : 'Khóa kỳ công', context: `${period.month} · bản chốt gần nhất v${period.revision}. ${locked ? 'Bản chốt cũ tiếp tục được giữ lại. Sửa xong cần chốt phiên bản mới.' : allowUnresolved ? 'Bạn đã chọn chốt kèm ngoại lệ. Ca thiếu vẫn chưa xác định công.' : 'Chỉ chốt khi dữ liệu đủ và cửa sổ nhận lượt của kỳ đã kết thúc.'}`,
      endpoint: `${root}/periods/${period.month}/${locked ? 'reopen' : 'lock'}`, body: { expected_revision: period.revision, ...(!locked ? { allow_unresolved: allowUnresolved } : {}) } });
  }
  async function confirm(reason: string) {
    if (!action) return;
    setBusy(true); setError(''); setSuccess('');
    try { const body = await api(action.endpoint, { method: 'POST', body: JSON.stringify({ ...action.body, reason }) }); setPeriod(body); setAction(null); setSuccess(body.status === 'locked' ? `Đã khóa kỳ ${body.month}, bản chốt v${body.revision}.` : 'Đã mở lại kỳ. Bản chốt cũ được giữ để đối chiếu.'); setSelected(body.status === 'locked' ? body.revision : 'preview'); setAllowUnresolved(false); }
    catch (error) { setError(errorText(error)); }
    finally { setBusy(false); }
  }
  const range = monthRange(month);
  return <section className="time-controls">
    <p className="section-explanation">Khóa kỳ tạo bản lưu bất biến theo phiên bản. Mở lại cần lý do; bản lưu trước đó vẫn xem được. Chỉ khóa kỳ đã kết thúc và hết cửa sổ nhận lượt của các ca trong kỳ.</p>
    {error && <p className="error" role="alert">{error}</p>}{success && <p className="success" role="status">{success}</p>}
    <form className="time-period-filter" onSubmit={event => { event.preventDefault(); void load(); }}><label>Kỳ công<input type="month" value={month} onChange={event => changed(event.target.value)} required disabled={busy} /></label><button disabled={loading || busy}>{loading ? 'Đang tải…' : 'Tải trạng thái kỳ'}</button></form>
    {period && <>
      <div className="time-control-card"><h2>Kỳ {period.month} · {period.status === 'locked' ? 'Đã khóa' : 'Đang mở'}</h2><p className="section-explanation">Đã có {period.snapshots.length} bản chốt · Múi giờ {timezone || 'đang tải…'}.</p>
        {period.status !== 'locked' && <label className="time-check"><input type="checkbox" checked={allowUnresolved} onChange={event => setAllowUnresolved(event.target.checked)} disabled={busy} />Cho phép chốt kèm ngoại lệ còn thiếu/chưa gắn ca; giữ nguyên trạng thái chưa xác định công</label>}
        <div className="time-actions"><button onClick={begin} disabled={busy}>{period.status === 'locked' ? 'Mở lại kỳ có lý do' : 'Khóa kỳ có lý do'}</button><button className="text-button" onClick={() => setSelected('preview')} disabled={busy}>Xem trước theo dữ liệu hiện tại</button></div>
      </div>
      <h2>Các bản chốt đã lưu</h2><div className="employee-table"><table><thead><tr><th>Phiên bản</th><th>Thời điểm chốt</th><th>Lý do</th><th>Số ca / phút đủ dữ liệu</th><th>Xem</th></tr></thead><tbody>{period.snapshots.map(row => <tr key={row.revision}><td>v{row.revision}{period.status === 'locked' && period.revision === row.revision && ' · hiện hành'}</td><td>{timezone && formatTime(row.created_at, timezone)}</td><td className="time-wrap">{row.reason}</td><td>{row.summary.row_count} / {(row.summary.worked_seconds / 60).toLocaleString('vi-VN', {maximumFractionDigits:2})}</td><td><button className="text-button" onClick={() => setSelected(row.revision)}>Xem bản v{row.revision}</button></td></tr>)}{!period.snapshots.length && <tr><td colSpan={5}>Chưa có bản chốt.</td></tr>}</tbody></table></div>
      {selected !== null && range && <div className="time-period-report"><h2>{selected === 'preview' ? `Xem trước kỳ ${period.month}` : `Bản chốt kỳ ${period.month} · v${selected}`}</h2><TimesheetsPanel key={`${period.month}-${selected}`} {...props} range={range} frozen={selected === 'preview' ? undefined : { month: period.month, revision: selected }} /></div>}
    </>}
    {action && <ReasonDialog action={action} busy={busy} error={error} onCancel={() => setAction(null)} onSubmit={confirm} />}
  </section>;
}

function monthRange(month: string) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return null;
  const [year, number] = month.split('-').map(Number);
  const days = new Date(Date.UTC(year, number, 0)).getUTCDate();
  return { from: month + '-01', to: month + '-' + String(days).padStart(2, '0') };
}
