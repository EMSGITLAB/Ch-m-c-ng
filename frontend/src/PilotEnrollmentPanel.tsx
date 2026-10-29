import { useEffect, useState } from 'react';

type PilotState = { revision: number; active: boolean; policy_id: string | null; enabled: boolean; included: boolean; participants: number; threshold: number | null; minimum_margin: number | null };

export function PilotEnrollmentPanel({ employeeId, csrf, onChanged, onUnauthorized }: { employeeId: string; csrf: string; onChanged: () => void; onUnauthorized: () => void }) {
  const [state, setState] = useState<PilotState | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const endpoint = `/api/admin/recognition/pilot/employees/${employeeId}`;

  useEffect(() => {
    const controller = new AbortController();
    setState(null);
    void fetch(endpoint, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]) })
      .then(async response => {
        const body = await response.json();
        if (response.status === 401) onUnauthorized();
        if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Chưa đọc được trạng thái chấm công thử.');
        if (!controller.signal.aborted) setState(body);
      }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Chưa kết nối được máy chủ.'); });
    return () => controller.abort();
  }, [endpoint, refresh]);

  async function publish(remove: boolean) {
    if (!state) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const response = await fetch(endpoint + (remove ? '/remove' : '/enroll'), {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ expected_revision: state.revision, expected_policy_id: state.policy_id }),
        signal: AbortSignal.timeout(60000),
      });
      const body = await response.json();
      if (response.status === 401) onUnauthorized();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Chưa cập nhật được cấu hình.');
      setMessage(`${remove ? 'Đã loại khỏi danh sách nhận diện' : 'Đã đưa bộ mẫu tham chiếu mới nhất vào nhận diện'}. Cấu hình hiện có ${body.participants} hồ sơ. Không cần khởi động lại.`);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Chưa xác nhận được cập nhật. Hãy kiểm tra trạng thái trước khi thử lại.');
    } finally {
      setBusy(false); setRefresh(value => value + 1);
    }
  }

  return <section className="pilot-enrollment" aria-label="Đưa mẫu vào chấm công thử">
    <h3>Đưa mẫu vào chấm công thử</h3>
    <p className="section-explanation">Dùng bộ mẫu tham chiếu đã hoàn tất mới nhất của hồ sơ, từ camera hoặc ảnh nhập đạt chất lượng. Máy chủ giữ nguyên ngưỡng đã thử và kiểm tra lại các ảnh hiệu chỉnh hiện có trước khi đổi cấu hình. Một ảnh tham chiếu hợp lệ có thể dùng để bắt đầu.</p>
    {state && <>
      <p>{state.enabled && state.included ? 'Hồ sơ đang có trong danh sách nhận diện.' : state.included ? 'Đã có mẫu; cấu hình đang dừng.' : 'Hồ sơ chưa có trong danh sách nhận diện hiện tại.'} Danh sách có {state.participants} hồ sơ hợp lệ.</p>
      {state.policy_id ? <p className="section-explanation">Ngưỡng {state.threshold?.toFixed(4)} · khoảng cách ứng viên {state.minimum_margin?.toFixed(4)}. Chưa nghiệm thu độ chính xác theo nhóm và chống ảnh giả.</p> : <p className="section-explanation">Cần thiết lập cấu hình thử ban đầu từ ảnh tham chiếu và một ảnh camera mới trước khi thêm danh sách.</p>}
      <div className="form-actions">
        <button type="button" disabled={busy || !state.active || !state.policy_id} onClick={() => void publish(false)}>{busy ? 'Đang cập nhật…' : state.included ? 'Cập nhật bộ mẫu vào chấm công thử' : 'Đưa mẫu vào chấm công thử'}</button>
        <button type="button" className="secondary" disabled={busy || !state.included} onClick={() => void publish(true)}>Loại khỏi danh sách nhận diện</button>
      </div>
    </>}
    {message && <p className="success" role="status">{message}</p>}
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}
