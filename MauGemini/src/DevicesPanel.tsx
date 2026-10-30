import { useEffect, useState, type FormEvent } from 'react';

type Device = { id: string; name: string; direction: 'in' | 'out'; active: boolean; paired: boolean; last_seen_at: string | null };
type Pairing = { device: Device; pairing_code: string; expires_at: string };

export function DevicesPanel({ csrf, onUnauthorized }: { csrf: string; onUnauthorized: () => void }) {
  const [items, setItems] = useState<Device[]>([]);
  const [name, setName] = useState('');
  const [direction, setDirection] = useState<'in' | 'out'>('in');
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);

  // Local browser pairing state
  const [currentKiosk, setCurrentKiosk] = useState<Device | null>(null);
  const [pairingInputCode, setPairingInputCode] = useState('');
  const [pairingSuccess, setPairingSuccess] = useState('');
  const [pairingError, setPairingError] = useState('');
  const [pairingBusy, setPairingBusy] = useState(false);

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

  // Check current browser pairing
  useEffect(() => {
    fetch('/api/kiosk/device')
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (d?.paired && d.active) setCurrentKiosk(d);
        else setCurrentKiosk(null);
      })
      .catch(() => setCurrentKiosk(null));
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const body = await request('/api/admin/devices', { signal: controller.signal });
        if (!controller.signal.aborted) setItems(body.items || []);
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Không tải được thiết bị.');
      }
    }
    load();
    const timer = setInterval(load, 10000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [csrf, refresh]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await request('/api/admin/devices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, direction }),
      });
      setPairing(result);
      setName('');
      setRefresh(n => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thêm được thiết bị.');
    } finally {
      setBusy(false);
    }
  }

  async function change(device: Device, action: 'pairing' | 'revoke') {
    setBusy(true);
    setError('');
    try {
      const result = await request(`/api/admin/devices/${device.id}/${action}`, { method: 'POST' });
      setPairing(action === 'pairing' ? result : null);
      setRefresh(n => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không cập nhật được thiết bị.');
    } finally {
      setBusy(false);
    }
  }

  async function handlePairThisBrowser(event: FormEvent) {
    event.preventDefault();
    setPairingBusy(true);
    setPairingError('');
    setPairingSuccess('');
    try {
      const response = await fetch('/api/kiosk/pair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Kiosk-Intent': 'pair-local-kiosk' },
        body: JSON.stringify({ code: pairingInputCode }),
        signal: AbortSignal.timeout(15000),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(typeof result.detail === 'string' ? result.detail : 'Mã ghép cần đủ 8 chữ số hợp lệ.');
      }
      setCurrentKiosk(result);
      window.dispatchEvent(new Event('kiosk-device-changed'));
      setPairingSuccess(`Đã ghép thành công thiết bị này với điểm: "${result.name}"`);
      setPairingInputCode('');
      setRefresh(n => n + 1);
    } catch (e) {
      setPairingError(e instanceof Error ? e.message : 'Không ghép được thiết bị.');
    } finally {
      setPairingBusy(false);
    }
  }

  return (
    <div className="devices-panel">
      {/* 1. Local Browser Kiosk Setup Card (Moved inside Admin) */}
      <section className="admin-subcard pairing-local-card" aria-label="Thiết lập điểm chấm công cho tablet này">
        <div className="subcard-header">
          <div>
            <h3>Cấu hình điểm chấm công cho thiết bị (Tablet này)</h3>
            <p>Xác thực quyền điểm danh tự động cho trình duyệt của tablet hoặc iPad này.</p>
          </div>
          {currentKiosk ? (
            <span className="status-label valid">Đã ghép thành công</span>
          ) : (
            <span className="status-label inactive">Chưa ghép điểm chấm công</span>
          )}
        </div>

        {currentKiosk ? (
          <div className="paired-device-info">
            <div className="paired-badge-row">
              <span className="paired-icon">📱</span>
              <div>
                <strong>{currentKiosk.name}</strong>
                <div className="paired-sub">
                  <span>Chiều: {currentKiosk.direction === 'in' ? 'Vào ca' : 'Ra ca'}</span>
                  <span> · Trạng thái: Sẵn sàng nhận diện</span>
                </div>
              </div>
            </div>
            <p className="paired-note">
              Thiết bị này đã được cấp quyền điểm danh tự động cho nhân viên tại màn hình Kiosk.
            </p>
          </div>
        ) : (
          <form className="browser-pairing-form" onSubmit={handlePairThisBrowser}>
            <p className="form-hint">
              Nhập mã ghép 8 chữ số (được tạo ở bảng bên dưới) để kích hoạt tablet này thành điểm chấm công.
            </p>
            <div className="pairing-form-row">
              <input
                value={pairingInputCode}
                onChange={e => setPairingInputCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
                inputMode="numeric"
                pattern="[0-9]{8}"
                minLength={8}
                maxLength={8}
                placeholder="Nhập mã 8 số (Ví dụ: 12345678)"
                required
              />
              <button className="primary-pill-btn" disabled={pairingBusy}>
                {pairingBusy ? 'Đang ghép…' : 'Kích hoạt tablet này'}
              </button>
            </div>
            {pairingError && <div className="error" role="alert">{pairingError}</div>}
            {pairingSuccess && <div className="success" role="status">{pairingSuccess}</div>}
          </form>
        )}
      </section>

      {/* 2. Registered Devices Management */}
      <section className="admin-subcard" aria-label="Danh sách thiết bị toàn hệ thống">
        <div className="subcard-header">
          <div>
            <h3>Danh sách thiết bị điểm danh toàn hệ thống</h3>
            <p>Mỗi điểm chấm công có mã ghép riêng dùng một lần để ủy quyền cho tablet.</p>
          </div>
        </div>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        <form className="device-create" onSubmit={create}>
          <label>
            Tên thiết bị mới
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Ví dụ: iPad Cửa bảo vệ 1"
              minLength={2}
              maxLength={100}
              required
            />
          </label>
          <label>
            Chiều điểm danh mặc định
            <select value={direction} onChange={e => setDirection(e.target.value as 'in' | 'out')}>
              <option value="in">Vào ca</option>
              <option value="out">Ra ca</option>
            </select>
          </label>
          <button className="primary-pill-btn" disabled={busy}>
            {busy ? 'Đang tạo…' : '+ Tạo thiết bị & sinh mã ghép'}
          </button>
        </form>

        {pairing && (
          <section className="pairing-result" aria-label="Mã ghép thiết bị mới">
            <div className="pairing-result-box">
              <span>Mã ghép kích hoạt cho {pairing.device.name}</span>
              <strong className="pairing-code-digits">{pairing.pairing_code}</strong>
              <p>
                Mã có hiệu lực đến{' '}
                {new Date(pairing.expires_at).toLocaleTimeString('vi-VN', {
                  hour: '2-digit',
                  minute: '2-digit',
                  timeZone: 'Asia/Ho_Chi_Minh',
                })}
                . Nhập mã này vào ô “Kích hoạt tablet này” phía trên để liên kết.
              </p>
              <button className="text-button" onClick={() => setPairing(null)}>
                Đã ghi nhận ✕
              </button>
            </div>
          </section>
        )}

        <div className="employee-table">
          <table>
            <thead>
              <tr>
                <th>Tên thiết bị</th>
                <th>Chiều mặc định</th>
                <th>Trạng thái kết nối</th>
                <th>Thao tác quản trị</th>
              </tr>
            </thead>
            <tbody>
              {items.map(dev => (
                <tr key={dev.id}>
                  <td>
                    <strong>{dev.name}</strong>
                  </td>
                  <td>
                    <span className={`direction-badge ${dev.direction}`}>
                      {dev.direction === 'in' ? '↓ Vào ca' : '↑ Ra ca'}
                    </span>
                  </td>
                  <td>
                    <span className={'status-label ' + (!dev.active ? 'inactive' : dev.paired ? 'valid' : 'warning')}>
                      {!dev.active ? 'Đã thu hồi' : dev.paired ? 'Đã ghép' : 'Chưa ghép mã'}
                    </span>
                  </td>
                  <td>
                    {dev.active ? (
                      <div className="table-actions-cell">
                        <button className="text-button" onClick={() => change(dev, 'pairing')} disabled={busy}>
                          Tạo lại mã ghép
                        </button>
                        <button className="text-button danger" onClick={() => change(dev, 'revoke')} disabled={busy}>
                          Thu hồi
                        </button>
                      </div>
                    ) : (
                      <span className="muted-text">Không khả dụng</span>
                    )}
                  </td>
                </tr>
              ))}
              {!items.length && (
                <tr>
                  <td colSpan={4} className="empty-state">
                    Chưa có thiết bị nào. Tạo thiết bị mới để sinh mã ghép đầu tiên.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
