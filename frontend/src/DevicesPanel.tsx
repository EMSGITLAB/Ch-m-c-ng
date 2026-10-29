import { useEffect, useState, type FormEvent } from 'react';

type Device = { id: string; name: string; direction: 'in' | 'out'; active: boolean; paired: boolean; last_seen_at: string | null };
type Pairing = { device: Device; pairing_code: string; expires_at: string };

export function DevicesPanel({ csrf, onUnauthorized }: { csrf: string; onUnauthorized: () => void }) {
  const [items, setItems] = useState<Device[]>([]);
  const [name, setName] = useState('');
  const [direction, setDirection] = useState('in');
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);

  async function request(url: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers);
    headers.set('X-CSRF-Token', csrf);
    const response = await fetch(url, { ...options, headers, signal: options.signal || AbortSignal.timeout(15000) });
    const body = await response.json();
    if (!response.ok) {
      if (response.status === 401) onUnauthorized();
      throw new Error(typeof body.detail === 'string' ? body.detail : 'Dữ liệu thiết bị chưa hợp lệ.');
    }
    return body;
  }

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try { const body = await request('/api/admin/devices', { signal: controller.signal }); if (!controller.signal.aborted) setItems(body.items); }
      catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Không tải được thiết bị.'); }
    }
    load();
    const timer = setInterval(load, 10000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [csrf, refresh]);

  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const result = await request('/api/admin/devices', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, direction }) });
      setPairing(result); setName(''); setRefresh(n => n + 1);
    } catch (e) { setError(e instanceof Error ? e.message : 'Không thêm được thiết bị.'); }
    finally { setBusy(false); }
  }

  async function change(device: Device, action: 'pairing' | 'revoke') {
    setBusy(true); setError('');
    try {
      const result = await request(`/api/admin/devices/${device.id}/${action}`, { method: 'POST' });
      setPairing(action === 'pairing' ? result : null); setRefresh(n => n + 1);
    } catch (e) { setError(e instanceof Error ? e.message : 'Không cập nhật được thiết bị.'); }
    finally { setBusy(false); }
  }

  return <div className="devices-panel">
    <p className="section-explanation">Mỗi điểm chấm công có quyền riêng. Tạo thiết bị, rồi nhập mã ghép trên trình duyệt của thiết bị đó.</p>
    {error && <div className="error" role="alert">{error}</div>}
    <form className="device-create" onSubmit={create}>
      <label>Tên thiết bị<input value={name} onChange={e => setName(e.target.value)} placeholder="Ví dụ: Camera cửa vào" minLength={2} maxLength={100} required /></label>
      <label>Chiều chấm công<select value={direction} onChange={e => setDirection(e.target.value)}><option value="in">Vào ca</option><option value="out">Ra ca</option></select></label>
      <button disabled={busy}>{busy ? 'Đang xử lý…' : 'Tạo mã ghép thiết bị'}</button>
    </form>
    {pairing && <section className="pairing-result" aria-label="Mã ghép thiết bị">
      <span>Mã ghép cho {pairing.device.name}</span><strong>{pairing.pairing_code}</strong>
      <p>Mã dùng một lần, hết hạn lúc {new Date(pairing.expires_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' })}. Mở mục “Thiết lập điểm chấm công” ở trang Chấm công để nhập mã.</p>
      <button className="text-button" onClick={() => setPairing(null)}>Ẩn mã</button>
    </section>}
    <div className="employee-table"><table><thead><tr><th>Thiết bị</th><th>Chiều</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>
      {items.map(device => <tr key={device.id}><td>{device.name}</td><td>{device.direction === 'in' ? 'Vào ca' : 'Ra ca'}</td><td><span className={'status-label ' + (!device.active ? 'inactive' : '')}>{!device.active ? 'Đã thu hồi' : device.paired ? 'Đã ghép' : 'Chưa ghép'}</span></td><td>{device.active && <><button className="text-button" onClick={() => change(device, 'pairing')} disabled={busy}>Ghép lại</button><button className="text-button danger" onClick={() => change(device, 'revoke')} disabled={busy}>Thu hồi</button></>}</td></tr>)}
      {!items.length && <tr><td colSpan={4} className="empty-state">Chưa có thiết bị. Tạo mã ghép để thiết lập điểm chấm công đầu tiên.</td></tr>}
    </tbody></table></div>
    <p className="import-hint">Ghép lại sẽ ngắt quyền ghép cũ. Thu hồi sẽ dừng quyền của thiết bị ngay lập tức.</p>
  </div>;
}
