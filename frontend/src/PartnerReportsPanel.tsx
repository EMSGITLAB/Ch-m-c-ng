import { useEffect, useState, type FormEvent } from 'react';
import { localDateISO } from './dates';
import { changedReportFields, localDateTimeInput, reportRows, type ReportRow } from './partnerReportView';
import './partner-reports.css';

type Vendor = { id: string; name: string; code: string };
type Batch = {
  id: string;
  partner_id: string;
  name: string;
  site: string;
  work_date: string;
  state: string;
  timezone: string;
};
type Report = {
  source_hash: string;
  as_of: string;
  closed: boolean;
  closed_at?: string;
  closed_by?: number;
  close_reason?: string;
  partner: Vendor;
  batch: Batch;
  rows: ReportRow[];
  summary: {
    requested: number;
    capacity: number;
    admitted: number;
    complete: number;
    incomplete: number;
    pending: number;
    available_slots: number;
    total_worked_seconds: number;
  };
  note: string;
};
type Edit = {
  row: ReportRow;
  source: string;
  requestId: string;
  name: string;
  in_local: string;
  out_local: string;
  reason: string;
};

const labels: Record<string, string> = {
  draft: 'Nháp',
  open: 'Đang tiếp nhận',
  running: 'Đang thực hiện',
  review: 'Chờ đối soát',
  closed: 'Đã chốt',
};

const hours = (seconds: number | null) =>
  seconds === null ? '—' : (seconds / 3600).toLocaleString('vi-VN', { maximumFractionDigits: 2 });

export function PartnerReportsPanel({
  vendors,
  csrf,
  onUnauthorized,
  onClosed,
  refreshKey = 0,
  selectedBatchId,
  defaultDate,
  onSelectBatch,
}: {
  vendors: Vendor[];
  csrf: string;
  onUnauthorized: () => void;
  onClosed: () => void;
  refreshKey?: number;
  selectedBatchId?: string;
  defaultDate?: string;
  onSelectBatch?: (batchId: string) => void;
}) {
  const initialDay = defaultDate || localDateISO();
  const [range, setRange] = useState({ from: initialDay, to: initialDay, partner: '', site: '' });
  const [batches, setBatches] = useState<Batch[]>([]);
  const [batch, setBatch] = useState(selectedBatchId || '');
  const [batchPage, setBatchPage] = useState(0);
  const [moreBatches, setMoreBatches] = useState(false);
  const [result, setResult] = useState<Report | null>(null);
  const [filter, setFilter] = useState('all');
  const [page, setPage] = useState(0);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [edit, setEdit] = useState<Edit | null>(null);
  const [detail, setDetail] = useState<ReportRow | null>(null);
  const [closeReason, setCloseReason] = useState('');
  const [ack, setAck] = useState(false);
  const [closeId, setCloseId] = useState(crypto.randomUUID());

  useEffect(() => {
    if (defaultDate && defaultDate !== range.from && defaultDate !== range.to) {
      setRange(prev => ({ ...prev, from: defaultDate, to: defaultDate }));
      setBatchPage(0);
    }
  }, [defaultDate]);

  useEffect(() => {
    if (selectedBatchId && batches.some(row => row.id === selectedBatchId)) {
      setBatch(selectedBatchId);
    }
  }, [selectedBatchId, batches]);

  async function api(path: string, options: RequestInit = {}) {
    const response = await fetch('/api/admin/partners' + path, {
      ...options,
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...options.headers },
      signal: options.signal || AbortSignal.timeout(20000),
    });
    const body = await response.json();
    if (response.status === 401) onUnauthorized();
    if (!response.ok)
      throw new Error(
        typeof body.detail === 'string' ? body.detail : 'Dữ liệu chưa hợp lệ. Kiểm tra ngày/giờ và lý do.'
      );
    return body;
  }

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const query = new URLSearchParams({
      date_from: range.from,
      date_to: range.to,
      offset: String(batchPage * 50),
    });
    if (range.partner) query.set('partner_id', range.partner);
    if (range.site) query.set('site', range.site);
    api('/batches/list?' + query, { signal: controller.signal })
      .then(body => {
        if (active) {
          setBatches(body.items);
          setMoreBatches(body.has_more);
          setBatch(value => {
            if (selectedBatchId && body.items.some((row: Batch) => row.id === selectedBatchId)) {
              return selectedBatchId;
            }
            return body.items.some((row: Batch) => row.id === value) ? value : body.items[0]?.id || '';
          });
          setError('');
        }
      })
      .catch(err => {
        if (active) setError(err instanceof Error ? err.message : 'Chưa tải được đợt.');
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [range.from, range.to, range.partner, range.site, batchPage, refresh, refreshKey, csrf]);

  useEffect(() => {
    setEdit(null);
    setDetail(null);
    setCloseReason('');
    setAck(false);
    setCloseId(crypto.randomUUID());
    setPage(0);
    setResult(null);
  }, [batch]);

  useEffect(() => {
    setBatch('');
    setBatches([]);
    setResult(null);
    setEdit(null);
    setDetail(null);
  }, [range.from, range.to, range.partner, range.site, batchPage]);

  useEffect(() => {
    if (!batch) return;
    let active = true;
    const controller = new AbortController();
    api(`/batches/${batch}/report`, { signal: controller.signal })
      .then(body => {
        if (active) {
          setResult(body);
          setError('');
        }
      })
      .catch(err => {
        if (active) {
          setResult(null);
          setError(err instanceof Error ? err.message : 'Chưa tải được báo cáo.');
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [batch, refresh, refreshKey, csrf]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!edit || !result || busy) return;
    const changes = changedReportFields(edit.row, edit, result.batch.timezone);
    if (!Object.keys(changes).length) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await api(`/workers/${edit.row.worker_id}/adjustments`, {
        method: 'POST',
        body: JSON.stringify({
          request_id: edit.requestId,
          expected_source: edit.source,
          reason: edit.reason,
          ...changes,
        }),
      });
      setEdit(null);
      setDetail(null);
      setMessage('Đã lưu điều chỉnh; lượt camera gốc được giữ nguyên.');
      setRefresh(value => value + 1);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Chưa rõ kết quả; tải lại bảng/lịch sử trước khi gửi yêu cầu khác.'
      );
    } finally {
      setBusy(false);
    }
  }

  async function close() {
    if (!result || busy) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const saved = await api(`/batches/${result.batch.id}/close`, {
        method: 'POST',
        body: JSON.stringify({
          request_id: closeId,
          expected_source: result.source_hash,
          reason: closeReason,
          acknowledge_incomplete: ack,
        }),
      });
      setResult(saved);
      setEdit(null);
      setMessage('Đã chốt đợt. Bản chốt được giữ riêng và không còn sửa trực tiếp.');
      onClosed();
      setRefresh(value => value + 1);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Chưa rõ kết quả chốt; tải lại trạng thái trước khi thử lại.'
      );
    } finally {
      setBusy(false);
    }
  }

  const rows = result ? reportRows(result.rows, filter) : [];
  const time = (value: string | null) =>
    value
      ? new Date(value).toLocaleString('vi-VN', {
          timeZone: result?.batch.timezone || 'Asia/Ho_Chi_Minh',
          hour12: false,
        })
      : '—';
  const changes = edit && result ? changedReportFields(edit.row, edit, result.batch.timezone) : {};

  return (
    <div className="admin-subcard partner-card partner-reports">
      <div className="subcard-header">
        <div>
          <h2>Đối soát ca làm việc & Xuất bảng công</h2>
          <p>
            Kiểm tra cặp Vào/Ra của từng mã lao động tạm. Lưu ý: “Chưa ghi lượt Ra” chỉ phản ánh thiếu lượt quét, không khẳng định còn ở sàn.
          </p>
        </div>
        <button
          type="button"
          className="secondary-pill-btn"
          disabled={busy}
          onClick={() => {
            setEdit(null);
            setDetail(null);
            setRefresh(value => value + 1);
          }}
        >
          ↻ Làm mới
        </button>
      </div>

      <div className="partner-report-filters">
        <label>
          Từ ngày
          <input
            type="date"
            value={range.from}
            disabled={busy}
            onChange={event => {
              setRange({ ...range, from: event.target.value });
              setBatchPage(0);
            }}
          />
        </label>
        <label>
          Đến ngày
          <input
            type="date"
            value={range.to}
            disabled={busy}
            onChange={event => {
              setRange({ ...range, to: event.target.value });
              setBatchPage(0);
            }}
          />
        </label>
        <label>
          Đối tác
          <select
            value={range.partner}
            disabled={busy}
            onChange={event => {
              setRange({ ...range, partner: event.target.value });
              setBatchPage(0);
            }}
          >
            <option value="">Tất cả đối tác</option>
            {vendors.map(vendor => (
              <option key={vendor.id} value={vendor.id}>
                {vendor.code} · {vendor.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Sàn / vị trí
          <input
            maxLength={120}
            placeholder="Lọc theo tên sàn / cổng"
            value={range.site}
            disabled={busy}
            onChange={event => {
              setRange({ ...range, site: event.target.value });
              setBatchPage(0);
            }}
          />
        </label>
        <label>
          Đợt / ca đối soát
          <select
            value={batch}
            disabled={busy}
            onChange={event => {
              setBatch(event.target.value);
              onSelectBatch?.(event.target.value);
            }}
          >
            <option value="">Chọn đợt</option>
            {batches.map(row => (
              <option key={row.id} value={row.id}>
                {row.work_date} · {row.name} · {row.site} · {labels[row.state] || row.state}
              </option>
            ))}
          </select>
        </label>
      </div>

      {(batchPage > 0 || moreBatches) && (
        <div className="pagination">
          <span>Trang đợt {batchPage + 1}</span>
          <div className="pagination-controls">
            <button
              type="button"
              className="text-button"
              disabled={busy || batchPage === 0}
              onClick={() => setBatchPage(value => value - 1)}
            >
              ← Đợt trang trước
            </button>
            <button
              type="button"
              className="text-button"
              disabled={busy || !moreBatches}
              onClick={() => setBatchPage(value => value + 1)}
            >
              Đợt trang tiếp →
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}

      {result && (
        <>
          <div className="partner-report-batch-banner">
            <div>
              <h3>
                {result.partner.name} · {result.batch.name} ({result.batch.work_date})
              </h3>
              <p>
                {result.batch.site} · Múi giờ {result.batch.timezone} · Cập nhật lúc {time(result.as_of)} — {result.note}
              </p>
            </div>
            <span className={`status-label ${result.closed ? 'inactive' : 'valid'}`}>
              {result.closed ? '🔒 Đã chốt' : labels[result.batch.state] || result.batch.state}
            </span>
          </div>

          <dl className="partner-report-stats">
            <div>
              <dt>Yêu cầu / hạn mức</dt>
              <dd>
                {result.summary.requested} / {result.summary.capacity}
              </dd>
            </div>
            <div>
              <dt>Đã Vào</dt>
              <dd>{result.summary.admitted}</dd>
            </div>
            <div>
              <dt>Đủ Vào/Ra</dt>
              <dd>{result.summary.complete}</dd>
            </div>
            <div>
              <dt>Thiếu cặp</dt>
              <dd>{result.summary.incomplete}</dd>
            </div>
            <div>
              <dt>Đang tiếp nhận</dt>
              <dd>{result.summary.pending}</dd>
            </div>
            <div>
              <dt>Tổng giờ công</dt>
              <dd>{hours(result.summary.total_worked_seconds)}h</dd>
            </div>
          </dl>

          <div className="admin-tools partner-options">
            <label className="filter-label">
              <span>Lọc trạng thái dòng</span>
              <select
                value={filter}
                onChange={event => {
                  setFilter(event.target.value);
                  setPage(0);
                }}
              >
                <option value="all">Tất cả ({result.rows.length})</option>
                <option value="complete">Đủ Vào/Ra ({result.summary.complete})</option>
                <option value="incomplete">Đã Vào nhưng thiếu cặp ({result.summary.incomplete})</option>
                <option value="pending">Chờ / hủy / hết phiên ({result.summary.pending})</option>
              </select>
            </label>
            <a
              className="secondary-pill-btn"
              href={`/api/admin/partners/batches/${batch}/export.csv?expected_source=${result.source_hash}&status=${filter}`}
              download
            >
              ⬇ Xuất CSV bản đang xem
            </a>
          </div>

          {detail && (
            <div className="partner-report-detail">
              <div className="subcard-header">
                <h3>{detail.code} — Lượt gốc và lịch sử điều chỉnh</h3>
                <button type="button" className="text-button" onClick={() => setDetail(null)}>
                  Đóng chi tiết ✕
                </button>
              </div>
              <p>
                Vào camera gốc: <strong>{time(detail.raw_in_at)}</strong> · Ra camera gốc:{' '}
                <strong>{time(detail.raw_out_at)}</strong>
              </p>
              <ul>
                {detail.original_events.map(event => (
                  <li key={event.id}>
                    {event.direction === 'in' ? 'Vào' : 'Ra'} · {time(event.server_time)} · {event.id}
                  </li>
                ))}
              </ul>
              <ol>
                {detail.adjustments.map(item => (
                  <li key={item.revision}>
                    Lần {item.revision} · {time(item.at)} · Quản trị #{item.admin_id}: {item.reason}
                    <pre>{JSON.stringify(item.overrides, null, 2)}</pre>
                  </li>
                ))}
              </ol>
              {!detail.adjustments.length && <p>Chưa có điều chỉnh thủ công nào.</p>}
            </div>
          )}

          {edit && (
            <form onSubmit={save} className="partner-edit-report">
              <div className="subcard-header">
                <div>
                  <h3>Điều chỉnh đối soát: {edit.row.code}</h3>
                  <p>
                    Giờ nhập theo {result.batch.timezone}. Bỏ trống thời gian để loại giờ đó khỏi bảng đối soát; lượt gốc camera vẫn được lưu.
                  </p>
                </div>
                <button
                  type="button"
                  className="text-button"
                  disabled={busy}
                  onClick={() => setEdit(null)}
                >
                  Đóng ✕
                </button>
              </div>
              <div className="partner-input-row three-cols">
                <label>
                  Họ tên đối soát
                  <input
                    required
                    maxLength={160}
                    value={edit.name}
                    disabled={busy}
                    onChange={event => setEdit({ ...edit, name: event.target.value })}
                  />
                </label>
                <label>
                  Giờ Vào đối soát
                  <input
                    type="datetime-local"
                    step="1"
                    value={edit.in_local}
                    disabled={busy}
                    onChange={event => setEdit({ ...edit, in_local: event.target.value })}
                  />
                </label>
                <label>
                  Giờ Ra đối soát
                  <input
                    type="datetime-local"
                    step="1"
                    value={edit.out_local}
                    disabled={busy}
                    onChange={event => setEdit({ ...edit, out_local: event.target.value })}
                  />
                </label>
              </div>
              <label>
                Lý do điều chỉnh (tối thiểu 5 ký tự)
                <input
                  required
                  minLength={5}
                  maxLength={500}
                  placeholder="Nhập lý do điều chỉnh giờ công / họ tên..."
                  value={edit.reason}
                  disabled={busy}
                  onChange={event => setEdit({ ...edit, reason: event.target.value })}
                />
              </label>
              <div className="form-actions">
                <button
                  className="primary-pill-btn"
                  disabled={busy || edit.reason.trim().length < 5 || !Object.keys(changes).length}
                >
                  {busy ? 'Đang lưu…' : 'Lưu điều chỉnh'}
                </button>
                <button
                  type="button"
                  className="secondary-pill-btn"
                  disabled={busy}
                  onClick={() => setEdit(null)}
                >
                  Hủy
                </button>
              </div>
            </form>
          )}

          <div className="employee-table">
            <table>
              <thead>
                <tr>
                  <th>Mã tạm / họ tên</th>
                  <th>Trạng thái</th>
                  <th>Vào đối soát</th>
                  <th>Ra đối soát</th>
                  <th>Giờ công</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(page * 50, (page + 1) * 50).map(row => (
                  <tr key={row.worker_id}>
                    <td>
                      <strong>{row.code}</strong>
                      <div className="partner-cell-sub">{row.name || 'Chưa xác nhận tên'}</div>
                    </td>
                    <td>
                      <span
                        className={`status-label ${
                          row.status === 'complete' ? 'valid' : row.admitted ? 'warning' : 'inactive'
                        }`}
                      >
                        {row.status_label}
                      </span>
                      {row.adjustment_revision > 0 && (
                        <small className="partner-policy-note">
                          Đã điều chỉnh {row.adjustment_revision} lần
                        </small>
                      )}
                    </td>
                    <td>{time(row.in_at)}</td>
                    <td>{time(row.out_at)}</td>
                    <td>
                      <strong>{hours(row.worked_seconds)}</strong>
                    </td>
                    <td>
                      <div className="table-actions-cell">
                        <button type="button" className="text-button" onClick={() => setDetail(row)}>
                          Gốc & lịch sử
                        </button>
                        {!result.closed && result.batch.state === 'review' && row.admitted && (
                          <button
                            type="button"
                            className="text-button"
                            disabled={busy}
                            onClick={() => {
                              setEdit({
                                row,
                                source: result.source_hash,
                                requestId: crypto.randomUUID(),
                                name: row.name || '',
                                in_local: localDateTimeInput(row.in_at, result.batch.timezone),
                                out_local: localDateTimeInput(row.out_at, result.batch.timezone),
                                reason: '',
                              });
                              setError('');
                            }}
                          >
                            Điều chỉnh
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {!rows.length && (
                  <tr>
                    <td colSpan={6} className="empty-state">
                      Không có lao động thuộc bộ lọc này.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {rows.length > 50 && (
            <div className="pagination">
              <span>
                {rows.length} dòng · Trang {page + 1}
              </span>
              <div className="pagination-controls">
                <button
                  type="button"
                  className="text-button"
                  disabled={page === 0}
                  onClick={() => setPage(value => value - 1)}
                >
                  ← Dòng trang trước
                </button>
                <button
                  type="button"
                  className="text-button"
                  disabled={(page + 1) * 50 >= rows.length}
                  onClick={() => setPage(value => value + 1)}
                >
                  Dòng trang tiếp →
                </button>
              </div>
            </div>
          )}

          {result.closed ? (
            <div className="partner-close-note">
              <strong>
                🔒 Đã chốt lúc {time(result.closed_at || null)} · Quản trị #{result.closed_by}
              </strong>
              <p>{result.close_reason}</p>
            </div>
          ) : (
            result.batch.state === 'review' && (
              <div className="partner-close-note">
                <h3>Chốt đợt công đối tác</h3>
                <p>
                  Bản chốt lưu riêng cả dữ liệu gốc và điều chỉnh; sau khi chốt không sửa trực tiếp hoặc mở lại đợt này.
                </p>
                <label>
                  Lý do / ghi chú chốt (tối thiểu 5 ký tự)
                  <input
                    minLength={5}
                    maxLength={500}
                    placeholder="Ví dụ: Đã đối soát biên bản xác nhận ca với quản lý đối tác"
                    value={closeReason}
                    disabled={busy}
                    onChange={event => setCloseReason(event.target.value)}
                  />
                </label>
                {result.summary.incomplete > 0 && (
                  <label className="partner-check">
                    <input
                      type="checkbox"
                      checked={ack}
                      disabled={busy}
                      onChange={event => setAck(event.target.checked)}
                    />
                    <span>
                      Tôi đã kiểm tra và xác nhận chốt {result.summary.incomplete} dòng còn thiếu Vào/Ra; các dòng này
                      không được tự tính đủ công.
                    </span>
                  </label>
                )}
                <div>
                  <button
                    className="primary-pill-btn"
                    disabled={busy || closeReason.trim().length < 5 || (result.summary.incomplete > 0 && !ack)}
                    onClick={() => void close()}
                  >
                    {busy ? 'Đang chốt…' : '✓ Chốt bản đối soát này'}
                  </button>
                </div>
              </div>
            )
          )}
        </>
      )}

      {!batch && (
        <p className="empty-state">
          Chưa có đợt phù hợp bộ lọc. Tạo và cấu hình đợt trước khi tiếp nhận lao động.
        </p>
      )}
    </div>
  );
}
