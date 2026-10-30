import { useEffect, useState, type FormEvent } from 'react';
import './partner.css';
import { PartnerAdmissionPanel } from './PartnerAdmissionPanel';
import { PartnerReportsPanel } from './PartnerReportsPanel';

type Vendor = { id: string; code: string; name: string; active: boolean };
type Batch = {
  id: string;
  partner_id: string;
  name: string;
  site: string;
  work_date: string;
  state: string;
  capacity: number;
  starts_at: string;
  ends_at: string;
  timezone: string;
  retention_hours: number;
  threshold: number | null;
};
type Device = { id: string; name: string; active: boolean; direction: string };
type Binding = { device_id: string; batch_id: string; active: boolean };

const labels: Record<string, string> = {
  draft: 'Nháp',
  open: 'Đang tiếp nhận',
  running: 'Đang thực hiện',
  review: 'Chờ đối soát',
  closed: 'Đã chốt',
};

const stateBadgeClass: Record<string, string> = {
  draft: 'inactive',
  open: 'valid',
  running: 'trial',
  review: 'warning',
  closed: 'inactive',
};

const transitions: Record<string, { state: string; title: string }[]> = {
  draft: [{ state: 'open', title: 'Mở tiếp nhận' }],
  open: [
    { state: 'running', title: 'Dừng nhận người mới' },
    { state: 'review', title: 'Chuyển đối soát' },
  ],
  running: [{ state: 'review', title: 'Chuyển đối soát' }],
  review: [],
  closed: [],
};

const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' });

type SubSection = 'batches' | 'admissions' | 'reports' | 'setup';

export function PartnerAdminPanel({ csrf, onUnauthorized }: { csrf: string; onUnauthorized: () => void }) {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [day, setDay] = useState(today);
  const [selectedBatchId, setSelectedBatchId] = useState('');
  const [showQuickCreateBatch, setShowQuickCreateBatch] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reason, setReason] = useState('');
  const [vendor, setVendor] = useState({ code: '', name: '' });
  const [draft, setDraft] = useState({
    request_id: crypto.randomUUID(),
    partner_id: '',
    work_date: today(),
    name: 'Ca tăng cường',
    site: '',
    start: '08:00',
    end: '17:00',
    capacity: 30,
    requested_count: 30,
  });
  const [pause, setPause] = useState({ enabled: false, start: '12:00', end: '13:00', paid: false });
  const [binding, setBinding] = useState({ device_id: '', batch_id: '' });
  const [capacities, setCapacities] = useState<Record<string, number>>({});
  const [more, setMore] = useState(false);
  const [page, setPage] = useState(0);
  const [subSection, setSubSection] = useState<SubSection>('batches');

  async function request(path: string, options: RequestInit = {}) {
    const response = await fetch('/api/admin/' + path, {
      ...options,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...options.headers },
    });
    const body = await response.json();
    if (response.status === 401) onUnauthorized();
    if (!response.ok)
      throw new Error(
        typeof body.detail === 'string'
          ? body.detail
          : 'Dữ liệu chưa hợp lệ. Kiểm tra các trường và thử lại.'
      );
    return body;
  }

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      request('partners', { signal: controller.signal }),
      request(`partners/batches/list?date_from=${day}&date_to=${day}&offset=${page * 50}`, {
        signal: controller.signal,
      }),
      request('devices', { signal: controller.signal }),
      request('partners/devices/list', { signal: controller.signal }),
    ])
      .then(([vs, bs, ds, links]) => {
        if (controller.signal.aborted) return;
        setVendors(vs.items);
        setBatches(bs.items);
        setMore(bs.has_more);
        setDevices(ds.items);
        setBindings(links.items);
        setSelectedBatchId(prev =>
          bs.items.some((b: Batch) => b.id === prev) ? prev : bs.items[0]?.id || ''
        );
        setDraft(value => ({
          ...value,
          partner_id: value.partner_id || vs.items.find((v: Vendor) => v.active)?.id || '',
        }));
      })
      .catch(e => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : 'Chưa tải được dữ liệu đối tác.');
      });
    return () => controller.abort();
  }, [day, page, refresh, csrf]);

  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await action();
      setRefresh(value => value + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Chưa lưu được dữ liệu.');
    } finally {
      setBusy(false);
    }
  }

  function createVendor(event: FormEvent) {
    event.preventDefault();
    void perform(async () => {
      const saved = await request('partners', { method: 'POST', body: JSON.stringify(vendor) });
      setDraft(value => ({ ...value, partner_id: saved.id }));
      setVendor({ code: '', name: '' });
      setMessage('Đã tạo đối tác.');
    });
  }

  function createBatch(event: FormEvent) {
    event.preventDefault();
    void perform(async () => {
      const created = await request('partners/batches', {
        method: 'POST',
        body: JSON.stringify({
          ...draft,
          breaks: pause.enabled ? [{ start: pause.start, end: pause.end, paid: pause.paid }] : [],
        }),
      });
      setDay(draft.work_date);
      setPage(0);
      if (created?.id) {
        setSelectedBatchId(created.id);
      }
      setDraft(value => ({ ...value, request_id: crypto.randomUUID() }));
      setShowQuickCreateBatch(false);
      setSubSection('batches');
      setMessage('Đã tạo đợt nháp. Mở tiếp nhận sau khi kiểm tra cấu hình.');
    });
  }

  function bindDevice(event: FormEvent) {
    event.preventDefault();
    void perform(async () => {
      await request('partners/devices/' + binding.device_id, {
        method: 'PUT',
        body: JSON.stringify({ batch_id: binding.batch_id, reason }),
      });
      setMessage('Đã gán thiết bị cho đợt đối tác.');
    });
  }

  const activeVendorsCount = vendors.filter(v => v.active).length;
  const activeBatchesCount = batches.filter(b => ['open', 'running'].includes(b.state)).length;
  const activeBindings = bindings.filter(link => link.active);

  return (
    <section className="partner-admin" aria-label="Quản trị chấm công đối tác">
      {/* Compact Command Header */}
      <div className="admin-subcard partner-admin-overview">
        <div className="subcard-header partner-command-top">
          <div>
            <h3>Điều phối & Đối soát Chấm công Đối tác</h3>
            <p>
              Lao động thời vụ dùng mã & mẫu mặt tạm theo ca (tự xóa vector sau 48h kết thúc ca; bảng công lưu độc lập).
            </p>
          </div>
          <div className="partner-command-actions">
            <button
              type="button"
              className="primary-pill-btn"
              onClick={() => setShowQuickCreateBatch(prev => !prev)}
            >
              {showQuickCreateBatch ? '✕ Đóng tạo đợt' : '+ Tạo đợt / ca mới'}
            </button>
            <a className="secondary-pill-btn partner-open-kiosk-link" href="#partner">
              🤝 Mở Kiosk Đối tác →
            </a>
          </div>
        </div>

        {/* Compact 4-Metric Strip */}
        <div className="partner-kpi-strip">
          <div className="partner-kpi-pill">
            <span className="partner-kpi-label">Đơn vị đối tác</span>
            <strong>{activeVendorsCount}</strong>
            <small>/{vendors.length} đơn vị</small>
          </div>
          <div className="partner-kpi-pill">
            <span className="partner-kpi-label">Đợt ngày {day}</span>
            <strong>{batches.length}</strong>
            <small>{activeBatchesCount} đang mở/chạy</small>
          </div>
          <div className="partner-kpi-pill">
            <span className="partner-kpi-label">Kiosk đang gán</span>
            <strong>{activeBindings.length}</strong>
            <small>/{devices.filter(d => d.active).length} thiết bị</small>
          </div>
          <div className="partner-kpi-pill">
            <span className="partner-kpi-label">Lưu mẫu mặt tạm</span>
            <strong>48 giờ</strong>
            <small>Tự hủy sau ca</small>
          </div>
        </div>

        {/* Quick Collapsible Batch Creation Drawer */}
        {showQuickCreateBatch && (
          <form onSubmit={createBatch} className="partner-quick-drawer">
            <div className="subcard-header">
              <div>
                <h4>Khởi tạo nhanh đợt / ca tăng cường</h4>
                <p>Thiết lập khung giờ ca, sàn làm việc và hạn mức nhân sự tiếp nhận.</p>
              </div>
              {!vendors.length && (
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    setShowQuickCreateBatch(false);
                    setSubSection('setup');
                  }}
                >
                  Chưa có đối tác? Khai báo ngay →
                </button>
              )}
            </div>

            <div className="partner-input-row three-cols">
              <label>
                Đối tác cung ứng
                <select
                  required
                  value={draft.partner_id}
                  onChange={e => setDraft({ ...draft, partner_id: e.target.value })}
                >
                  <option value="">Chọn đối tác</option>
                  {vendors
                    .filter(v => v.active)
                    .map(v => (
                      <option key={v.id} value={v.id}>
                        {v.code} · {v.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Tên đợt / ca
                <input
                  required
                  minLength={2}
                  maxLength={100}
                  value={draft.name}
                  onChange={e => setDraft({ ...draft, name: e.target.value })}
                />
              </label>
              <label>
                Sàn / vị trí
                <input
                  required
                  minLength={2}
                  maxLength={120}
                  placeholder="Ví dụ: Kho B - Cổng 2"
                  value={draft.site}
                  onChange={e => setDraft({ ...draft, site: e.target.value })}
                />
              </label>
            </div>

            <div className="partner-input-row five-cols">
              <label>
                Ngày bắt đầu ca
                <input
                  required
                  type="date"
                  value={draft.work_date}
                  onChange={e => setDraft({ ...draft, work_date: e.target.value })}
                />
              </label>
              <label>
                Giờ bắt đầu
                <input
                  required
                  type="time"
                  value={draft.start}
                  onChange={e => setDraft({ ...draft, start: e.target.value })}
                />
              </label>
              <label>
                Giờ kết thúc
                <input
                  required
                  type="time"
                  value={draft.end}
                  onChange={e => setDraft({ ...draft, end: e.target.value })}
                />
              </label>
              <label>
                SL yêu cầu
                <input
                  required
                  type="number"
                  min={1}
                  max={5000}
                  value={draft.requested_count}
                  onChange={e => setDraft({ ...draft, requested_count: Number(e.target.value) })}
                />
              </label>
              <label>
                Hạn mức tối đa
                <input
                  required
                  type="number"
                  min={1}
                  max={5000}
                  value={draft.capacity}
                  onChange={e => setDraft({ ...draft, capacity: Number(e.target.value) })}
                />
              </label>
            </div>

            <div className="partner-drawer-footer">
              <div className="partner-drawer-checks">
                <label className="partner-check">
                  <input
                    type="checkbox"
                    checked={pause.enabled}
                    onChange={e => setPause({ ...pause, enabled: e.target.checked })}
                  />
                  <span>Có nghỉ giữa ca</span>
                </label>
                {pause.enabled && (
                  <div className="partner-inline-pause">
                    <input
                      required
                      type="time"
                      aria-label="Bắt đầu nghỉ"
                      value={pause.start}
                      onChange={e => setPause({ ...pause, start: e.target.value })}
                    />
                    <span>→</span>
                    <input
                      required
                      type="time"
                      aria-label="Kết thúc nghỉ"
                      value={pause.end}
                      onChange={e => setPause({ ...pause, end: e.target.value })}
                    />
                    <label className="partner-check">
                      <input
                        type="checkbox"
                        checked={pause.paid}
                        onChange={e => setPause({ ...pause, paid: e.target.checked })}
                      />
                      <span>Tính công giờ nghỉ</span>
                    </label>
                  </div>
                )}
              </div>
              <div className="partner-command-actions">
                <button
                  type="button"
                  className="secondary-pill-btn"
                  onClick={() => setShowQuickCreateBatch(false)}
                >
                  Hủy
                </button>
                <button className="primary-pill-btn" disabled={busy || !draft.partner_id}>
                  ✓ Lưu đợt nháp
                </button>
              </div>
            </div>
          </form>
        )}

        {/* Focused Workspace Tabs (No vertical dump) */}
        <div className="partner-subnav-bar" role="tablist" aria-label="Phân khu quản trị đối tác">
          <button
            type="button"
            role="tab"
            aria-selected={subSection === 'batches'}
            className={subSection === 'batches' ? 'active' : ''}
            onClick={() => setSubSection('batches')}
          >
            1. Điều phối Đợt & Thiết bị ({batches.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={subSection === 'admissions'}
            className={subSection === 'admissions' ? 'active' : ''}
            onClick={() => setSubSection('admissions')}
          >
            2. Giám sát Tiếp nhận
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={subSection === 'reports'}
            className={subSection === 'reports' ? 'active' : ''}
            onClick={() => setSubSection('reports')}
          >
            3. Đối soát & Xuất công
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={subSection === 'setup'}
            className={subSection === 'setup' ? 'active' : ''}
            onClick={() => setSubSection('setup')}
          >
            4. Danh mục Đối tác ({vendors.length})
          </button>
        </div>
      </div>

      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}

      {/* TAB 1: Batch Management & Device Binding */}
      {subSection === 'batches' && (
        <div className="admin-subcard partner-card">
          <div className="subcard-header">
            <div>
              <h2>Điều phối Đợt công & Gán Kiosk</h2>
              <p>
                Chọn ngày làm việc, nhập lý do thao tác trước khi mở tiếp nhận, cập nhật hạn mức hoặc gán Kiosk cho đợt.
              </p>
            </div>
          </div>

          <div className="admin-tools partner-batch-toolbar">
            <label className="filter-label">
              <span>Ngày công cần xem</span>
              <input
                type="date"
                required
                value={day}
                onChange={e => {
                  if (e.target.value) {
                    setDay(e.target.value);
                    setPage(0);
                  }
                }}
              />
            </label>
            <label className="search-label">
              <span>Lý do thao tác trạng thái / hạn mức / thiết bị (tối thiểu 5 ký tự)</span>
              <input
                minLength={5}
                maxLength={500}
                value={reason}
                onChange={e => setReason(e.target.value)}
                placeholder="Nhập lý do trước khi bấm thao tác (Ví dụ: Mở ca sáng kho lạnh)"
              />
            </label>
          </div>

          <div className="employee-table">
            <table>
              <thead>
                <tr>
                  <th>Đợt / đối tác</th>
                  <th>Khung giờ ca</th>
                  <th>Trạng thái</th>
                  <th>Hạn mức</th>
                  <th>Thao tác & Truy cập nhanh</th>
                </tr>
              </thead>
              <tbody>
                {batches.map(batch => (
                  <tr
                    key={batch.id}
                    className={selectedBatchId === batch.id ? 'partner-row-selected' : ''}
                  >
                    <td>
                      <strong>{batch.name}</strong>
                      <div className="partner-cell-sub">
                        {vendors.find(v => v.id === batch.partner_id)?.code} · {batch.site}
                      </div>
                    </td>
                    <td>
                      {new Date(batch.starts_at).toLocaleString('vi-VN', { timeZone: batch.timezone })}
                      <br />
                      {new Date(batch.ends_at).toLocaleString('vi-VN', { timeZone: batch.timezone })}
                    </td>
                    <td>
                      <span className={`status-label ${stateBadgeClass[batch.state] || 'trial'}`}>
                        {labels[batch.state] || batch.state}
                      </span>
                      <small className="partner-policy-note">
                        {batch.threshold === null
                          ? 'Chưa ghim cấu hình nhận diện'
                          : 'Đã ghim ngưỡng vận hành'}
                      </small>
                    </td>
                    <td>
                      <div className="partner-capacity-cell">
                        <input
                          aria-label={`Hạn mức ${batch.name}`}
                          type="number"
                          min={1}
                          max={5000}
                          value={capacities[batch.id] ?? batch.capacity}
                          onChange={e => setCapacities({ ...capacities, [batch.id]: Number(e.target.value) })}
                        />
                        <button
                          type="button"
                          className="text-button"
                          disabled={
                            busy || reason.trim().length < 5 || ['review', 'closed'].includes(batch.state)
                          }
                          onClick={() =>
                            void perform(async () => {
                              await request(`partners/batches/${batch.id}/capacity`, {
                                method: 'POST',
                                body: JSON.stringify({
                                  expected_capacity: batch.capacity,
                                  capacity: capacities[batch.id] ?? batch.capacity,
                                  reason,
                                }),
                              });
                              setMessage('Đã cập nhật hạn mức.');
                            })
                          }
                        >
                          Lưu
                        </button>
                      </div>
                    </td>
                    <td>
                      <div className="table-actions-cell">
                        {transitions[batch.state]?.map(action => (
                          <button
                            key={action.state}
                            type="button"
                            className="text-button"
                            disabled={busy || reason.trim().length < 5}
                            onClick={() =>
                              void perform(async () => {
                                await request(`partners/batches/${batch.id}/state`, {
                                  method: 'POST',
                                  body: JSON.stringify({
                                    expected_state: batch.state,
                                    state: action.state,
                                    reason,
                                  }),
                                });
                                setMessage('Đã cập nhật trạng thái đợt.');
                              })
                            }
                          >
                            {action.title}
                          </button>
                        ))}
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => {
                            setSelectedBatchId(batch.id);
                            setSubSection('admissions');
                          }}
                        >
                          Tiếp nhận →
                        </button>
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => {
                            setSelectedBatchId(batch.id);
                            setSubSection('reports');
                          }}
                        >
                          Đối soát →
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!batches.length && (
                  <tr>
                    <td colSpan={5} className="empty-state">
                      Chưa có đợt trong ngày {day}. Bấm <strong>“+ Tạo đợt / ca mới”</strong> ở góc trên để khởi tạo.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {(page > 0 || more) && (
            <div className="pagination">
              <span>Trang {page + 1}</span>
              <div className="pagination-controls">
                <button
                  type="button"
                  className="text-button"
                  disabled={busy || page === 0}
                  onClick={() => setPage(value => value - 1)}
                >
                  ← Trang trước
                </button>
                <button
                  type="button"
                  className="text-button"
                  disabled={busy || !more}
                  onClick={() => setPage(value => value + 1)}
                >
                  Trang tiếp →
                </button>
              </div>
            </div>
          )}

          <div className="partner-binding-section">
            <form onSubmit={bindDevice} className="partner-binding-form">
              <h3>Gán thiết bị Kiosk cho đợt đối tác</h3>
              <label>
                Thiết bị Kiosk
                <select
                  required
                  value={binding.device_id}
                  onChange={e => setBinding({ ...binding, device_id: e.target.value })}
                >
                  <option value="">Chọn thiết bị</option>
                  {devices
                    .filter(d => d.active)
                    .map(d => (
                      <option key={d.id} value={d.id}>
                        {d.name} · {d.direction === 'in' ? 'Vào' : 'Ra'}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Đợt / ca
                <select
                  required
                  value={binding.batch_id}
                  onChange={e => setBinding({ ...binding, batch_id: e.target.value })}
                >
                  <option value="">Chọn đợt</option>
                  {batches
                    .filter(b => !['review', 'closed'].includes(b.state))
                    .map(b => (
                      <option key={b.id} value={b.id}>
                        {b.name} · {vendors.find(v => v.id === b.partner_id)?.code}
                      </option>
                    ))}
                </select>
              </label>
              <button className="primary-pill-btn" disabled={busy || reason.trim().length < 5}>
                Gán cho đợt đối tác
              </button>
            </form>

            {activeBindings.length > 0 && (
              <div className="employee-table partner-compact-table">
                <table>
                  <thead>
                    <tr>
                      <th>Thiết bị Kiosk</th>
                      <th>Đợt đối tác đang gán</th>
                      <th>Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeBindings.map(link => (
                      <tr key={link.device_id}>
                        <td>
                          <strong>{devices.find(d => d.id === link.device_id)?.name || 'Thiết bị'}</strong>
                        </td>
                        <td>
                          <span className="status-label valid">
                            {batches.find(b => b.id === link.batch_id)?.name || 'Đợt ngoài ngày đang xem'}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="text-button danger"
                            disabled={busy || reason.trim().length < 5}
                            onClick={() =>
                              void perform(async () => {
                                await request(`partners/devices/${link.device_id}/unbind`, {
                                  method: 'POST',
                                  body: JSON.stringify({ reason }),
                                });
                                setMessage('Đã bỏ gán thiết bị đối tác.');
                              })
                            }
                          >
                            Bỏ gán
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: Live Partner Admissions Monitor */}
      {subSection === 'admissions' && (
        <PartnerAdmissionPanel
          batches={batches}
          selectedBatchId={selectedBatchId}
          onSelectBatch={setSelectedBatchId}
          onUnauthorized={onUnauthorized}
        />
      )}

      {/* TAB 3: Partner Reconciliation & Reports */}
      {subSection === 'reports' && (
        <PartnerReportsPanel
          vendors={vendors}
          csrf={csrf}
          onUnauthorized={onUnauthorized}
          refreshKey={refresh}
          selectedBatchId={selectedBatchId}
          defaultDate={day}
          onSelectBatch={setSelectedBatchId}
          onClosed={() => setRefresh(value => value + 1)}
        />
      )}

      {/* TAB 4: Partner Vendors Directory & Batch Setup */}
      {subSection === 'setup' && (
        <div className="partner-setup-grid">
          <form onSubmit={createVendor} className="admin-subcard partner-card">
            <div className="subcard-header">
              <div>
                <h2>Đối tác cung cấp</h2>
                <p>Khai báo mã và tên công ty cung ứng lao động thời vụ.</p>
              </div>
              <span className="status-label valid">{vendors.length} đơn vị</span>
            </div>

            <div className="partner-form-stack">
              <div className="partner-input-row">
                <label>
                  Mã đối tác
                  <input
                    required
                    maxLength={32}
                    pattern="[A-Za-z0-9_-]+"
                    placeholder="Ví dụ: VINALOG"
                    value={vendor.code}
                    onChange={e => setVendor({ ...vendor, code: e.target.value })}
                  />
                </label>
                <label>
                  Tên đối tác
                  <input
                    required
                    minLength={2}
                    maxLength={160}
                    placeholder="Ví dụ: Công ty Tiếp vận VinaLog"
                    value={vendor.name}
                    onChange={e => setVendor({ ...vendor, name: e.target.value })}
                  />
                </label>
              </div>
              <div>
                <button className="primary-pill-btn" disabled={busy}>
                  + Thêm đối tác
                </button>
              </div>
            </div>

            <div className="employee-table partner-compact-table">
              <table>
                <thead>
                  <tr>
                    <th>Mã ĐV</th>
                    <th>Tên đối tác</th>
                    <th>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {vendors.map(v => (
                    <tr key={v.id}>
                      <td>
                        <strong>{v.code}</strong>
                      </td>
                      <td>{v.name}</td>
                      <td>
                        <span className={`status-label ${v.active ? 'valid' : 'inactive'}`}>
                          {v.active ? 'Hoạt động' : 'Đã ngừng'}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {!vendors.length && (
                    <tr>
                      <td colSpan={3} className="empty-state">
                        Chưa có đối tác cung cấp nào.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </form>

          <form onSubmit={createBatch} className="admin-subcard partner-card">
            <div className="subcard-header">
              <div>
                <h2>Tạo đợt / ca tăng cường</h2>
                <p>Thiết lập khung giờ ca, sàn làm việc và hạn mức nhân sự tiếp nhận.</p>
              </div>
            </div>

            <div className="partner-form-stack">
              <div className="partner-input-row">
                <label>
                  Đối tác
                  <select
                    required
                    value={draft.partner_id}
                    onChange={e => setDraft({ ...draft, partner_id: e.target.value })}
                  >
                    <option value="">Chọn đối tác</option>
                    {vendors
                      .filter(v => v.active)
                      .map(v => (
                        <option key={v.id} value={v.id}>
                          {v.code} · {v.name}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Tên đợt / ca
                  <input
                    required
                    minLength={2}
                    maxLength={100}
                    value={draft.name}
                    onChange={e => setDraft({ ...draft, name: e.target.value })}
                  />
                </label>
              </div>

              <label>
                Sàn / vị trí
                <input
                  required
                  minLength={2}
                  maxLength={120}
                  placeholder="Ví dụ: Kho B - Cổng Tiếp Nhận 2"
                  value={draft.site}
                  onChange={e => setDraft({ ...draft, site: e.target.value })}
                />
              </label>

              <div className="partner-input-row three-cols">
                <label>
                  Ngày bắt đầu ca
                  <input
                    required
                    type="date"
                    value={draft.work_date}
                    onChange={e => setDraft({ ...draft, work_date: e.target.value })}
                  />
                </label>
                <label>
                  Số lao động yêu cầu
                  <input
                    required
                    type="number"
                    min={1}
                    max={5000}
                    value={draft.requested_count}
                    onChange={e => setDraft({ ...draft, requested_count: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Hạn mức được tiếp nhận
                  <input
                    required
                    type="number"
                    min={1}
                    max={5000}
                    value={draft.capacity}
                    onChange={e => setDraft({ ...draft, capacity: Number(e.target.value) })}
                  />
                </label>
              </div>

              <div className="partner-input-row">
                <label>
                  Giờ bắt đầu
                  <input
                    required
                    type="time"
                    value={draft.start}
                    onChange={e => setDraft({ ...draft, start: e.target.value })}
                  />
                </label>
                <label>
                  Giờ kết thúc
                  <input
                    required
                    type="time"
                    value={draft.end}
                    onChange={e => setDraft({ ...draft, end: e.target.value })}
                  />
                </label>
              </div>

              <p className="partner-hint-text">Giờ kết thúc trước giờ bắt đầu là ca qua đêm.</p>

              <label className="partner-check">
                <input
                  type="checkbox"
                  checked={pause.enabled}
                  onChange={e => setPause({ ...pause, enabled: e.target.checked })}
                />
                <span>Có nghỉ giữa ca</span>
              </label>

              {pause.enabled && (
                <div className="partner-pause-box">
                  <div className="partner-input-row">
                    <label>
                      Bắt đầu nghỉ
                      <input
                        required
                        type="time"
                        value={pause.start}
                        onChange={e => setPause({ ...pause, start: e.target.value })}
                      />
                    </label>
                    <label>
                      Kết thúc nghỉ
                      <input
                        required
                        type="time"
                        value={pause.end}
                        onChange={e => setPause({ ...pause, end: e.target.value })}
                      />
                    </label>
                  </div>
                  <label className="partner-check">
                    <input
                      type="checkbox"
                      checked={pause.paid}
                      onChange={e => setPause({ ...pause, paid: e.target.checked })}
                    />
                    <span>Khoảng nghỉ vẫn tính công</span>
                  </label>
                </div>
              )}

              <div>
                <button className="primary-pill-btn" disabled={busy || !draft.partner_id}>
                  + Tạo đợt nháp
                </button>
              </div>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}
