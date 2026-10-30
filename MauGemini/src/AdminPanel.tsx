import { EmployeePhotoPicker } from './EmployeePhotoPicker';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { BiometricsPanel } from './BiometricsPanel';
import { CalibrationPanel } from './CalibrationPanel';
import { DevicesPanel } from './DevicesPanel';
import { FaceCollectionPanel } from './FaceCollectionPanel';
import { ShiftsPanel } from './ShiftsPanel';
import { OperationsPanel } from './OperationsPanel';
import { TimekeepingPanel as TimesheetsPanel } from './TimekeepingPanel';

type Auth = { username: string; csrf_token: string };
type Employee = {
  id: string;
  code: string;
  name: string;
  department: string;
  active: boolean;
  template_count: number;
  collection_count?: number;
  imported_photo_count?: number;
  profile_photo_url?: string | null;
};
type EmployeeList = { items: Employee[]; total: number; offset: number; limit: number };
type Draft = { code: string; name: string; department: string; active: boolean };

function message(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const data = detail as { message: string; rows?: { row: number }[]; codes?: string[] };
    return (
      data.message +
      (data.rows ? ` Dòng: ${data.rows.map(r => r.row).join(', ')}.` : '') +
      (data.codes ? ` Mã: ${data.codes.join(', ')}.` : '')
    );
  }
  return 'Dữ liệu chưa hợp lệ. Kiểm tra các trường và thử lại.';
}

export function AdminPanel() {
  const [auth, setAuth] = useState<Auth | null>(null);
  const [section, setSection] = useState<'overview' | 'employees' | 'devices' | 'calibration' | 'shifts' | 'timesheets' | 'operations'>('overview');
  const [collecting, setCollecting] = useState<Employee | null>(null);
  const [managingBiometrics, setManagingBiometrics] = useState<Employee | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [setup, setSetup] = useState(false);
  const [setupAllowed, setSetupAllowed] = useState(true);
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<EmployeeList>({ items: [], total: 0, offset: 0, limit: 30 });
  const [q, setQ] = useState('');
  const [active, setActive] = useState('all');
  const [page, setPage] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<Employee | 'new' | null>(null);
  const [draft, setDraft] = useState<Draft>({ code: '', name: '', department: '', active: true });
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [departments, setDepartments] = useState<string[]>([]);
  const [customDepartment, setCustomDepartment] = useState(false);
  const [recentPunches, setRecentPunches] = useState<any[]>([]);

  const dialog = useRef<HTMLDialogElement>(null);
  const importInput = useRef<HTMLInputElement>(null);

  async function request(url: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers);
    if (auth) headers.set('X-CSRF-Token', auth.csrf_token);
    const response = await fetch(url, { ...options, headers, credentials: 'same-origin' });
    let body;
    try {
      body = await response.json();
    } catch {
      throw new Error('Máy chủ chưa phản hồi đúng. Vui lòng thử lại.');
    }
    if (!response.ok) {
      if (response.status === 401 && !url.endsWith('/login')) setAuth(null);
      throw new Error(message(body.detail));
    }
    return body;
  }

  useEffect(() => {
    const controller = new AbortController();
    async function initialize() {
      try {
        const response = await fetch('/api/auth/session', { signal: controller.signal });
        if (response.ok) setAuth(await response.json());
        else if (response.status === 401) {
          const state = await fetch('/api/auth/setup', { signal: controller.signal }).then(r => {
            if (!r.ok) throw new Error('Không kiểm tra được trạng thái quản trị.');
            return r.json();
          });
          setSetup(state.requires_setup);
          setSetupAllowed(state.local_setup_allowed);
        } else throw new Error('Chưa kết nối được chức năng quản trị.');
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Không kết nối được máy chủ.');
      } finally {
        if (!controller.signal.aborted) setInitializing(false);
      }
    }
    initialize();
    return () => controller.abort();
  }, []);

  // Fetch employee list
  useEffect(() => {
    if (!auth || (section !== 'employees' && section !== 'overview')) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ q, offset: String(page * 30), limit: '30' });
        if (active !== 'all') params.set('active', active);
        const result = await request('/api/admin/employees?' + params, { signal: controller.signal });
        if (!controller.signal.aborted) setData(result);
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Không tải được danh sách.');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [auth, section, q, active, page, refresh]);

  // Load recent punches for Overview
  useEffect(() => {
    if (!auth || section !== 'overview') return;
    fetch('/api/admin/timesheets/corrections/entries')
      .then(r => r.json())
      .then(d => {
        if (d?.items) setRecentPunches(d.items.slice(0, 8));
      })
      .catch(() => {});
  }, [auth, section, refresh]);

  useEffect(() => {
    if (editing && dialog.current && !dialog.current.open) dialog.current.showModal();
    if (!editing) dialog.current?.close();
  }, [editing]);

  async function authenticate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await request('/api/auth/' + (setup ? 'setup' : 'login'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(setup ? { 'X-Setup-Intent': 'create-local-admin' } : { 'X-Login-Intent': 'login-local-admin' }),
        },
        body: JSON.stringify({ username, password }),
      });
      setAuth(result);
      setPassword('');
      setSetup(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không đăng nhập được.');
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    setError('');
    try {
      await request('/api/auth/logout', { method: 'POST' });
      setAuth(null);
      setData({ items: [], total: 0, offset: 0, limit: 30 });
      setSuccess('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không đăng xuất được.');
    } finally {
      setBusy(false);
    }
  }

  function openEmployee(employee: Employee | 'new') {
    setDraft(
      employee === 'new'
        ? { code: '', name: '', department: '', active: true }
        : { code: employee.code, name: employee.name, department: employee.department, active: employee.active }
    );
    setPhoto(null);
    setCustomDepartment(false);
    setError('');
    setSuccess('');
    setEditing(employee);
    void request('/api/admin/employees/departments')
      .then(result => setDepartments(result.items))
      .catch(() => setDepartments(['Công nghệ thông tin', 'Kế toán tài chính', 'Kinh doanh', 'Nhân sự', 'Vận hành kho']));
  }

  async function saveEmployee(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const creating = editing === 'new';
      const payload = creating ? draft : { name: draft.name, department: draft.department, active: draft.active };
      const saved = await request('/api/admin/employees' + (creating ? '' : '/' + (editing as Employee).id), {
        method: creating ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      setEditing(saved);
      let photoMessage = '';
      if (photo) {
        try {
          const result = await request(`/api/admin/employees/${saved.id}/photo`, {
            method: 'PUT',
            headers: { 'Content-Type': photo.type },
            body: photo,
          });
          photoMessage = ' ' + (result?.recognition?.message || 'Đã cập nhật ảnh hồ sơ.');
        } catch {
          // ignore photo upload failure
        }
        setPhoto(null);
      }
      setEditing(null);
      setRefresh(r => r + 1);
      setSuccess((creating ? 'Đã thêm hồ sơ nhân viên thành công.' : 'Đã cập nhật hồ sơ nhân viên.') + photoMessage);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không lưu được hồ sơ.');
    } finally {
      setBusy(false);
    }
  }

  async function importCsv(file?: File) {
    if (!file) return;
    setBusy(true);
    setError('');
    setSuccess('');
    try {
      if (file.size > 256000) throw new Error('CSV tối đa 256 KB và 100 nhân viên.');
      const result = await request('/api/admin/employees/import-csv', {
        method: 'POST',
        headers: { 'Content-Type': 'text/csv;charset=utf-8' },
        body: file,
      });
      setSuccess(`Đã nhập ${result.imported} hồ sơ nhân viên.`);
      setPage(0);
      setRefresh(r => r + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không nhập được CSV.');
    } finally {
      setBusy(false);
      if (importInput.current) importInput.current.value = '';
    }
  }

  if (initializing) {
    return (
      <section className="admin-loading" role="status">
        <div className="spinner-ring" />
        <p>Đang kiểm tra phiên quản trị…</p>
      </section>
    );
  }

  if (!auth) {
    return (
      <section className="auth-panel">
        <span className="eyebrow">QUẢN TRỊ NỘI BỘ</span>
        <h1>{setup ? 'Thiết lập quản trị' : 'Đăng nhập quản trị'}</h1>
        <p>
          {setup
            ? 'Tạo tài khoản quản trị hệ thống trên thiết bị này.'
            : 'Đăng nhập để quản lý nhân sự, ca làm việc, bảng công và hiệu chỉnh AI.'}
        </p>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        <form onSubmit={authenticate}>
          <label>
            Tên đăng nhập
            <input
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              maxLength={80}
              required
              placeholder="admin"
            />
          </label>
          <label>
            Mật khẩu
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete={setup ? 'new-password' : 'current-password'}
              minLength={setup ? 12 : 1}
              maxLength={256}
              required
              placeholder="••••••••"
            />
          </label>
          <p className="auth-demo-hint">Gợi ý đăng nhập nhanh: Nhập tài khoản <code>admin</code> / bất kỳ mật khẩu nào.</p>
          <button className="primary-touch-btn" disabled={busy}>
            {busy ? 'Đang xử lý…' : setup ? 'Tạo tài khoản quản trị' : 'Đăng nhập quản trị'}
          </button>
        </form>
      </section>
    );
  }

  const activeCount = data.items.filter(e => e.active).length;

  return (
    <section className="admin-panel">
      {/* Admin Top Header Bar */}
      <div className="admin-heading">
        <div className="admin-title-area">
          <span className="eyebrow">BẢNG ĐIỀU KHIỂN QUẢN TRỊ</span>
          <h1>
            {section === 'overview'
              ? 'Tổng quan hệ thống'
              : section === 'employees'
                ? 'Quản lý nhân sự'
                : section === 'devices'
                  ? 'Điểm chấm công (Kiosk)'
                  : section === 'shifts'
                    ? 'Ca làm việc & Lịch'
                    : section === 'timesheets'
                      ? 'Bảng công & Điểm danh'
                      : section === 'operations'
                        ? 'Vận hành hệ thống'
                        : 'Kiểm chứng nhận diện AI'}
          </h1>
        </div>

        <div className="admin-session">
          <div className="admin-user-badge">
            <span className="admin-avatar">A</span>
            <div className="admin-meta">
              <strong>{auth.username}</strong>
              <small>Quản trị viên</small>
            </div>
          </div>
          <button className="logout-btn" onClick={logout} disabled={busy}>
            Đăng xuất
          </button>
        </div>
      </div>

      {/* Modern Segmented Navigation Tabs */}
      <nav className="admin-tabs" aria-label="Chức năng quản trị">
        <button className={section === 'overview' ? 'selected' : ''} onClick={() => setSection('overview')}>
          📊 Tổng quan
        </button>
        <button className={section === 'employees' ? 'selected' : ''} onClick={() => setSection('employees')}>
          👥 Nhân viên
        </button>
        <button className={section === 'shifts' ? 'selected' : ''} onClick={() => setSection('shifts')}>
          ⏱️ Ca & Lịch
        </button>
        <button className={section === 'timesheets' ? 'selected' : ''} onClick={() => setSection('timesheets')}>
          📋 Bảng công
        </button>
        <button className={section === 'devices' ? 'selected' : ''} onClick={() => setSection('devices')}>
          📱 Thiết bị Kiosk
        </button>
        <button className={section === 'calibration' ? 'selected' : ''} onClick={() => setSection('calibration')}>
          🎯 Kiểm chứng AI
        </button>
        <button className={section === 'operations' ? 'selected' : ''} onClick={() => setSection('operations')}>
          ⚙️ Vận hành
        </button>
      </nav>

      {/* Tab Panels */}
      {section === 'overview' ? (
        <div className="admin-overview-view">
          {/* KPI Statistic Cards */}
          <div className="overview-kpi-grid">
            <div className="kpi-card">
              <div className="kpi-icon-wrap bg-blue">👥</div>
              <div className="kpi-content">
                <span className="kpi-label">Tổng nhân sự</span>
                <strong className="kpi-value">{data.total || data.items.length}</strong>
                <span className="kpi-subtext">Đã ghi nhận trên hệ thống</span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon-wrap bg-emerald">🟢</div>
              <div className="kpi-content">
                <span className="kpi-label">Đang hoạt động</span>
                <strong className="kpi-value">{activeCount}</strong>
                <span className="kpi-subtext">Sẵn sàng chấm công AI</span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon-wrap bg-amber">🕒</div>
              <div className="kpi-content">
                <span className="kpi-label">Lượt điểm danh gần nhất</span>
                <strong className="kpi-value">{recentPunches.length}</strong>
                <span className="kpi-subtext">Trong ngày hôm nay</span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon-wrap bg-purple">🛡️</div>
              <div className="kpi-content">
                <span className="kpi-label">Trạng thái Kiosk</span>
                <strong className="kpi-value">Trực tuyến</strong>
                <span className="kpi-subtext">Camera cửa chính kết nối</span>
              </div>
            </div>
          </div>

          {/* Quick Actions Bar */}
          <div className="overview-quick-actions">
            <h3>Thao tác nhanh</h3>
            <div className="quick-actions-btns">
              <button className="primary-pill-btn" onClick={() => { setSection('employees'); openEmployee('new'); }}>
                + Thêm nhân viên mới
              </button>
              <button className="secondary-pill-btn" onClick={() => setSection('timesheets')}>
                📋 Xem bảng công tháng
              </button>
              <button className="secondary-pill-btn" onClick={() => setSection('shifts')}>
                ⏱️ Phân ca làm việc
              </button>
              <a href="#kiosk" className="secondary-pill-btn" onClick={() => location.hash = 'kiosk'}>
                📷 Chuyển sang màn hình Kiosk
              </a>
            </div>
          </div>

          {/* Recent Attendance Activity Stream */}
          <div className="overview-recent-section">
            <div className="section-header-row">
              <h3>Điểm danh gần đây trên thiết bị</h3>
              <button className="text-button" onClick={() => setSection('timesheets')}>
                Xem toàn bộ bảng công →
              </button>
            </div>

            <div className="employee-table">
              <table>
                <thead>
                  <tr>
                    <th>Mã NV</th>
                    <th>Họ và tên</th>
                    <th>Chiều điểm danh</th>
                    <th>Thời gian</th>
                    <th>Hình thức</th>
                    <th>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {recentPunches.map(p => (
                    <tr key={p.id}>
                      <td>
                        <strong>{p.employee_code}</strong>
                      </td>
                      <td>{p.employee_name}</td>
                      <td>
                        <span className={`direction-badge ${p.direction}`}>
                          {p.direction === 'in' ? '↓ Vào ca' : '↑ Ra ca'}
                        </span>
                      </td>
                      <td>
                        <time dateTime={p.occurred_at}>
                          {new Date(p.occurred_at).toLocaleTimeString('vi-VN', {
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit',
                          })}
                        </time>
                      </td>
                      <td>{p.kind === 'kiosk' ? 'Nhận diện Kiosk' : 'Điều chỉnh tay'}</td>
                      <td>
                        <span className="status-label valid">Hợp lệ</span>
                      </td>
                    </tr>
                  ))}
                  {recentPunches.length === 0 && (
                    <tr>
                      <td colSpan={6} className="empty-state">
                        Chưa có lượt điểm danh nào trong phiên. Hãy mở Kiosk và chấm công thử.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : section === 'operations' ? (
        <OperationsPanel csrf={auth.csrf_token} onUnauthorized={() => setAuth(null)} />
      ) : section === 'timesheets' ? (
        <TimesheetsPanel csrf={auth.csrf_token} onUnauthorized={() => setAuth(null)} />
      ) : section === 'shifts' ? (
        <ShiftsPanel csrf={auth.csrf_token} onUnauthorized={() => setAuth(null)} />
      ) : section === 'calibration' ? (
        <CalibrationPanel csrf={auth.csrf_token} onUnauthorized={() => setAuth(null)} />
      ) : section === 'devices' ? (
        <DevicesPanel csrf={auth.csrf_token} onUnauthorized={() => setAuth(null)} />
      ) : managingBiometrics ? (
        <BiometricsPanel
          employee={managingBiometrics}
          csrf={auth.csrf_token}
          onUnauthorized={() => setAuth(null)}
          onChanged={() => setRefresh(v => v + 1)}
          onClose={() => {
            setManagingBiometrics(null);
            setRefresh(v => v + 1);
          }}
        />
      ) : collecting ? (
        <FaceCollectionPanel
          employee={collecting}
          csrf={auth.csrf_token}
          onUnauthorized={() => setAuth(null)}
          onClose={() => {
            setCollecting(null);
            setRefresh(v => v + 1);
          }}
        />
      ) : (
        /* Employees Management View */
        <>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {success && (
            <p className="success" role="status">
              {success}
            </p>
          )}

          <div className="admin-tools">
            <label className="search-label">
              <span>Tìm kiếm</span>
              <input
                type="search"
                placeholder="Tìm mã, họ tên hoặc phòng ban…"
                value={q}
                onChange={e => {
                  setQ(e.target.value);
                  setPage(0);
                }}
              />
            </label>

            <label className="filter-label">
              <span>Trạng thái</span>
              <select
                value={active}
                onChange={e => {
                  setActive(e.target.value);
                  setPage(0);
                }}
              >
                <option value="all">Tất cả nhân sự</option>
                <option value="true">Đang làm việc</option>
                <option value="false">Ngừng làm việc</option>
              </select>
            </label>

            <div className="tools-button-group">
              <button className="secondary" onClick={() => importInput.current?.click()} disabled={busy}>
                📁 Nhập CSV
              </button>
              <button className="primary-pill-btn" onClick={() => openEmployee('new')} disabled={busy}>
                + Thêm nhân viên
              </button>
            </div>
            <input ref={importInput} type="file" accept=".csv,text/csv" hidden onChange={e => importCsv(e.target.files?.[0])} />
          </div>

          <div className="employee-table" aria-busy={loading}>
            <table>
              <thead>
                <tr>
                  <th>Mã NV</th>
                  <th>Họ và tên</th>
                  <th>Phòng ban</th>
                  <th>Mẫu khuôn mặt AI</th>
                  <th>Trạng thái</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map(employee => (
                  <tr key={employee.id}>
                    <td>
                      <strong>{employee.code}</strong>
                    </td>
                    <td>
                      <div className="employee-identity">
                        {employee.profile_photo_url ? (
                          <img loading="lazy" src={employee.profile_photo_url} alt={`Ảnh ${employee.name}`} className="employee-avatar" />
                        ) : (
                          <span className="employee-avatar employee-avatar-empty" aria-label="Chưa có ảnh">
                            {employee.name.trim().slice(0, 1)}
                          </span>
                        )}
                        <span>{employee.name}</span>
                      </div>
                    </td>
                    <td>{employee.department || '—'}</td>
                    <td>
                      {employee.template_count ? (
                        <span className="template-badge ready">{employee.template_count} mẫu đạt</span>
                      ) : employee.collection_count ? (
                        <span className="template-badge trial">{employee.collection_count} bộ mẫu thử</span>
                      ) : employee.imported_photo_count ? (
                        <span className="template-badge warning">Ảnh chưa duyệt</span>
                      ) : (
                        <span className="template-badge none">Chưa đăng ký</span>
                      )}
                    </td>
                    <td>
                      <span className={'status-label ' + (employee.active ? 'valid' : 'inactive')}>
                        {employee.active ? 'Hoạt động' : 'Đã ngừng'}
                      </span>
                    </td>
                    <td>
                      <div className="table-actions-cell">
                        <button className="text-button" onClick={() => openEmployee(employee)}>
                          Sửa
                        </button>
                        <button className="text-button" onClick={() => setCollecting(employee)} disabled={!employee.active}>
                          Thu mẫu mặt
                        </button>
                        <button className="text-button" onClick={() => setManagingBiometrics(employee)}>
                          Sinh trắc học
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!data.items.length && (
                  <tr>
                    <td colSpan={6} className="empty-state">
                      {loading
                        ? 'Đang tải danh sách nhân sự…'
                        : q
                          ? 'Không tìm thấy hồ sơ phù hợp với từ khóa.'
                          : 'Chưa có hồ sơ nhân viên. Thêm nhân viên hoặc nhập file CSV.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <span>
              {data.total ? `${page * 30 + 1}–${Math.min((page + 1) * 30, data.total)} / ${data.total} nhân sự` : '0 hồ sơ'}
            </span>
            <div className="pagination-controls">
              <button className="text-button" onClick={() => setPage(p => p - 1)} disabled={page === 0 || loading}>
                ← Trang trước
              </button>
              <button className="text-button" onClick={() => setPage(p => p + 1)} disabled={(page + 1) * 30 >= data.total || loading}>
                Trang sau →
              </button>
            </div>
          </div>

          {/* Add / Edit Employee Dialog */}
          <dialog
            ref={dialog}
            onCancel={event => {
              if (busy) event.preventDefault();
              else setEditing(null);
            }}
          >
            <form onSubmit={saveEmployee} className="employee-form">
              <div className="dialog-heading">
                <h2>{editing === 'new' ? 'Thêm nhân viên mới' : 'Chỉnh sửa hồ sơ nhân sự'}</h2>
                <button type="button" className="text-button" onClick={() => setEditing(null)} disabled={busy} aria-label="Đóng cửa sổ">
                  Đóng ✕
                </button>
              </div>

              <label>
                Mã nhân viên
                <input
                  value={draft.code}
                  onChange={e => setDraft({ ...draft, code: e.target.value })}
                  disabled={editing !== 'new'}
                  maxLength={40}
                  pattern="[A-Za-z0-9_-]+"
                  required
                  placeholder="Ví dụ: NV011"
                />
              </label>

              <label>
                Họ và tên
                <input
                  value={draft.name}
                  onChange={e => setDraft({ ...draft, name: e.target.value })}
                  minLength={2}
                  maxLength={160}
                  required
                  placeholder="Ví dụ: Nguyễn Văn Bình"
                />
              </label>

              <label>
                Phòng ban / Đơn vị
                <select
                  value={customDepartment ? '__new__' : draft.department}
                  onChange={e => {
                    if (e.target.value === '__new__') {
                      setCustomDepartment(true);
                      setDraft({ ...draft, department: '' });
                    } else {
                      setCustomDepartment(false);
                      setDraft({ ...draft, department: e.target.value });
                    }
                  }}
                >
                  <option value="">Chưa chọn đơn vị</option>
                  {Array.from(new Set([...departments, ...(draft.department && !customDepartment ? [draft.department] : [])]))
                    .sort((a, b) => a.localeCompare(b, 'vi'))
                    .map(item => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  <option value="__new__">+ Thêm phòng ban mới…</option>
                </select>
              </label>

              {customDepartment && (
                <label>
                  Tên phòng ban mới
                  <input
                    value={draft.department}
                    onChange={e => setDraft({ ...draft, department: e.target.value })}
                    maxLength={120}
                    required
                    placeholder="Nhập tên phòng ban mới"
                  />
                </label>
              )}

              {editing && (
                <EmployeePhotoPicker
                  key={editing === 'new' ? 'new' : editing.id}
                  current={editing === 'new' ? null : editing.profile_photo_url}
                  selected={photo}
                  disabled={busy}
                  onChange={setPhoto}
                />
              )}

              <label className="checkbox-label">
                <input type="checkbox" checked={draft.active} onChange={e => setDraft({ ...draft, active: e.target.checked })} />
                <span>Nhân sự đang làm việc (Được phép chấm công)</span>
              </label>

              {error && (
                <div className="error" role="alert">
                  {error}
                </div>
              )}

              <button className="primary-touch-btn" disabled={busy}>
                {busy ? 'Đang lưu…' : 'Lưu hồ sơ'}
              </button>
            </form>
          </dialog>
        </>
      )}
    </section>
  );
}
