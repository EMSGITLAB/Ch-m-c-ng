import { useEffect, useState } from 'react';
import type { PartnerWorker } from './partnerFlow';

export function PartnerAdmissionPanel({
  batches,
  selectedBatchId,
  onSelectBatch,
  onUnauthorized,
}: {
  batches: { id: string; name: string; site?: string; state?: string }[];
  selectedBatchId?: string;
  onSelectBatch?: (batchId: string) => void;
  onUnauthorized: () => void;
}) {
  const [batch, setBatch] = useState(selectedBatchId || '');
  const [workers, setWorkers] = useState<PartnerWorker[]>([]);
  const [page, setPage] = useState(0);
  const [more, setMore] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (selectedBatchId && batches.some(value => value.id === selectedBatchId)) {
      setBatch(selectedBatchId);
      setPage(0);
    } else if (!batches.some(value => value.id === batch)) {
      const nextId = batches[0]?.id || '';
      setBatch(nextId);
      onSelectBatch?.(nextId);
      setPage(0);
    }
  }, [batches, batch, selectedBatchId]);

  useEffect(() => {
    if (!batch) {
      setWorkers([]);
      return;
    }
    let active = true;
    let loading = false;
    const controller = new AbortController();
    async function load() {
      if (loading) return;
      loading = true;
      try {
        const response = await fetch(
          `/api/admin/partners/batches/${batch}/workers?offset=${page * 50}`,
          { signal: controller.signal }
        );
        const result = await response.json();
        if (!active) return;
        if (response.status === 401) onUnauthorized();
        if (!response.ok)
          throw new Error(
            typeof result.detail === 'string'
              ? result.detail
              : 'Chưa tải được danh sách tiếp nhận.'
          );
        setWorkers(result.items);
        setMore(result.has_more);
        setError('');
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Chưa tải được danh sách.');
      } finally {
        loading = false;
      }
    }
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => {
      active = false;
      controller.abort();
      clearInterval(timer);
    };
  }, [batch, page]);

  function getWorkerStatusBadge(worker: PartnerWorker) {
    if (worker.state === 'expired') return { label: 'Hết phiên', cls: 'inactive' };
    if (worker.state === 'cancelled') return { label: 'Đã hủy', cls: 'inactive' };
    if (worker.state === 'active') return { label: 'Đã Vào', cls: 'valid' };
    if (worker.state === 'completed') return { label: 'Đã Ra', cls: 'trial' };
    if (worker.name_confirmed) return { label: 'Đang hoàn tất Vào tự động', cls: 'warning' };
    return { label: 'Chờ họ tên', cls: 'warning' };
  }

  return (
    <div className="admin-subcard partner-card">
      <div className="subcard-header">
        <div>
          <h2>Theo dõi tiếp nhận tự động (Thời gian thực)</h2>
          <p>
            Người mới xác nhận họ tên tại kiosk, giữ mặt trước camera để hệ thống tự ghi Vào. Tự động làm mới mỗi 3 giây.
          </p>
        </div>
        <div className="partner-header-inline-controls">
          <label className="partner-inline-select">
            <span>Đợt đang xem:</span>
            <select
              value={batch}
              onChange={event => {
                const next = event.target.value;
                setBatch(next);
                onSelectBatch?.(next);
                setPage(0);
                setWorkers([]);
              }}
            >
              <option value="">Chọn đợt</option>
              {batches.map(value => (
                <option key={value.id} value={value.id}>
                  {value.name} {value.site ? `· ${value.site}` : ''}
                </option>
              ))}
            </select>
          </label>
          <span className="status-label valid">{workers.length} lao động</span>
        </div>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div className="employee-table">
        <table>
          <thead>
            <tr>
              <th>Mã tạm</th>
              <th>Họ tên</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {workers.map(worker => {
              const badge = getWorkerStatusBadge(worker);
              return (
                <tr key={worker.id}>
                  <td>
                    <strong>{worker.code}</strong>
                  </td>
                  <td>{worker.name || 'Đang đọc / nhập tên'}</td>
                  <td>
                    <span className={`status-label ${badge.cls}`}>{badge.label}</span>
                  </td>
                </tr>
              );
            })}
            {!workers.length && (
              <tr>
                <td colSpan={3} className="empty-state">
                  Chưa có người được tiếp nhận trong đợt / trang này.
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
              disabled={page === 0}
              onClick={() => setPage(value => value - 1)}
            >
              ← Trang trước
            </button>
            <button
              type="button"
              className="text-button"
              disabled={!more}
              onClick={() => setPage(value => value + 1)}
            >
              Trang tiếp →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
