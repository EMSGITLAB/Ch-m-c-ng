import { useEffect, useState } from 'react';
import { PilotEnrollmentPanel } from './PilotEnrollmentPanel';
import './imported-photos.css';

type Summary = { revision: number; active: boolean; current_model_id: string | null; imported_photos: number; templates_by_model: { model_id: string; count: number }[]; collections_by_model: { model_id: string; collections: number; samples: number }[] };
type ImportedPhoto = { id: string; accepted: boolean; feedback: string };
type ProbeResult = { reference_count: number; message: string; candidates: { employee_id: string; employee_code: string; employee_name: string; cosine: number; same_reference_file: boolean }[] };

export function BiometricsPanel({ employee, csrf, onClose, onChanged, onUnauthorized }: { employee: { id: string; code: string; name: string }; csrf: string; onClose: () => void; onChanged: () => void; onUnauthorized: () => void }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [code, setCode] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [photos, setPhotos] = useState<ImportedPhoto[]>([]);
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [probeBusy, setProbeBusy] = useState(false);
  const endpoint = `/api/admin/employees/${employee.id}/biometrics`;

  useEffect(() => {
    const controller = new AbortController();
    setSummary(null); setError('');
    fetch(endpoint, { signal: controller.signal }).then(async response => {
      const body = await response.json();
      if (response.status === 401) onUnauthorized();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Không đọc được dữ liệu khuôn mặt.');
      if (!controller.signal.aborted) setSummary(body);
    }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Chưa kết nối được máy chủ.'); });
    return () => controller.abort();
  }, [endpoint, refresh]);

  useEffect(() => {
    const controller = new AbortController();
    setPhotos([]); setProbe(null);
    fetch('/api/admin/imported-face-photos?' + new URLSearchParams({ employee_id: employee.id }), { signal: controller.signal }).then(async response => {
      if (response.status === 401) onUnauthorized();
      if (!response.ok) throw new Error('Chưa tải được các ảnh nhập.');
      const body = await response.json();
      if (!controller.signal.aborted) setPhotos(body.items);
    }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [employee.id, refresh]);

  async function testPhoto(file: File | undefined) {
    if (!file) return;
    setProbeBusy(true); setProbe(null); setError('');
    try {
      const response = await fetch('/api/admin/imported-face-photos/probe', { method: 'POST', headers: { 'Content-Type': file.type, 'X-CSRF-Token': csrf }, body: file, signal: AbortSignal.timeout(30000) });
      const body = await response.json();
      if (response.status === 401) onUnauthorized();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Ảnh chưa hợp lệ.');
      setProbe(body);
    } catch (e) { setError(e instanceof Error ? e.message : 'Chưa so sánh được ảnh.'); }
    finally { setProbeBusy(false); }
  }

  async function purge() {
    if (!summary) return;
    setBusy(true); setError(''); setSuccess('');
    try {
      const response = await fetch(endpoint + '/purge', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify({ confirm_employee_code: code, expected_revision: summary.revision, reason }), signal: AbortSignal.timeout(20000) });
      const body = await response.json();
      if (response.status === 401) onUnauthorized();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Không xóa được dữ liệu.');
      setSummary(null); setCode(''); setReason(''); setSuccess(body.message); setRefresh(value => value + 1); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : 'Chưa xác nhận được kết quả. Hãy tải lại trạng thái trước khi thử lại.'); }
    finally { setBusy(false); }
  }

  const templates = summary?.templates_by_model.reduce((count, row) => count + row.count, 0) || 0;
  const collections = summary?.collections_by_model.reduce((count, row) => count + row.collections, 0) || 0;
  const samples = summary?.collections_by_model.reduce((count, row) => count + row.samples, 0) || 0;
  const oldModels = summary && [...summary.templates_by_model, ...summary.collections_by_model].some(row => row.model_id !== summary.current_model_id);

  return <section className="biometrics-panel">
    <div className="collection-heading"><div><h2>Dữ liệu khuôn mặt</h2><p>{employee.code} · {employee.name}</p></div><button className="text-button" onClick={onClose} disabled={busy}>Về danh sách</button></div>
    <p className="section-explanation">Ngừng hoạt động hồ sơ sẽ loại người đó khỏi các lần nhận diện tiếp theo. Xóa dữ liệu khuôn mặt sẽ loại bỏ toàn bộ mẫu đăng ký, bộ hiệu chỉnh và bộ kiểm tra của hồ sơ trong database đang chạy.</p>
    {error && <p className="error" role="alert">{error}</p>}
    {success && <p className="success" role="status">{success}</p>}
    {summary ? <>
      <div className="employee-table"><table><thead><tr><th>Loại dữ liệu</th><th>Số lượng hiện có</th></tr></thead><tbody><tr><td>Mẫu nhận diện vận hành</td><td>{templates}</td></tr><tr><td>Bộ mẫu thu thập</td><td>{collections} bộ · {samples} mẫu</td></tr><tr><td>Hồ sơ</td><td>{summary.active ? 'Đang hoạt động' : 'Đã ngừng hoạt động'}</td></tr></tbody></table></div>
      {photos.length > 0 && <section className="imported-photo-section">
        <h3>Ảnh nhân viên đã nhập để thử nghiệm</h3>
        <div className="imported-photo-grid">{photos.map(photo => <figure key={photo.id}><img src={`/api/admin/imported-face-photos/${photo.id}/image`} alt={`Ảnh tham chiếu do người dùng cung cấp cho ${employee.name}`} /><figcaption><strong>{photo.accepted ? 'Đạt bộ lọc ban đầu' : 'Chưa đạt'}</strong><p>{photo.feedback}</p></figcaption></figure>)}</div>
        <p className="section-explanation">Ảnh gốc lưu trong database local cùng hồ sơ. Mẫu đạt đang dùng để thử nghiệm, chưa dùng ghi công. Xóa dữ liệu khuôn mặt bên dưới sẽ xóa cả ảnh nhập của hồ sơ này.</p>
      </section>}
      <section className="imported-photo-section">
        <h3>Thử so khớp với bộ ảnh nhập</h3>
        <p className="section-explanation">Chọn ảnh khác của nhân viên để kiểm tra thứ hạng trong toàn bộ bộ ảnh nhập. Điểm cosine là độ tương đồng, không phải tỷ lệ chính xác và không ghi công.</p>
        <label>Chọn ảnh thử (JPG, PNG, WebP)<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy || probeBusy} onChange={event => { void testPhoto(event.target.files?.[0]); event.target.value = ''; }} /></label>
        {probeBusy && <p role="status">Đang phân tích bằng model trên máy local…</p>}
        {probe && <div role="status"><p className="section-explanation">{probe.message} · {probe.reference_count} ảnh tham chiếu đang dùng.</p><div className="employee-table"><table><thead><tr><th>Gợi ý gần nhất</th><th>Điểm cosine</th><th>Ghi chú</th></tr></thead><tbody>{probe.candidates.map(candidate => <tr key={candidate.employee_id}><td>{candidate.employee_code} · {candidate.employee_name}</td><td>{candidate.cosine.toFixed(4)}</td><td>{candidate.same_reference_file ? 'Trùng chính tệp đã đăng ký — chỉ kiểm tra luồng xử lý' : 'Cần đối chiếu đúng người; chưa có kết luận nhận diện'}</td></tr>)}{!probe.candidates.length && <tr><td colSpan={3}>Chưa có mẫu ảnh nhập hợp lệ.</td></tr>}</tbody></table></div></div>}
      </section>
      {oldModels && <p className="section-explanation">Có dữ liệu thuộc model khác. Dữ liệu đó được giữ riêng và không dùng với model hiện tại; cần thu lại mẫu khi đổi model.</p>}
      <PilotEnrollmentPanel key={`${employee.id}:${refresh}`} employeeId={employee.id} csrf={csrf} onChanged={() => { setSuccess('Đã cập nhật cấu hình nhận diện thử.'); setRefresh(value => value + 1); onChanged(); }} onUnauthorized={onUnauthorized} />
      <h3>Xóa toàn bộ mẫu khuôn mặt của hồ sơ này</h3>
      <p className="section-explanation">Thao tác xóa không thể hoàn tác trong ứng dụng. Hồ sơ nhân viên và lịch sử chấm công vẫn được giữ lại. Bản sao lưu có vòng đời riêng và không bị xóa bởi thao tác này.</p>
      <form onSubmit={event => { event.preventDefault(); void purge(); }}>
        <label>Nhập mã {employee.code} để xác nhận<input value={code} onChange={event => setCode(event.target.value)} autoComplete="off" required disabled={busy} /></label>
        <label>Lý do xóa<input value={reason} onChange={event => setReason(event.target.value)} minLength={5} maxLength={500} required disabled={busy} /></label>
        <button className="danger" disabled={busy || code !== employee.code || reason.trim().length < 5 || !(templates + collections + summary.imported_photos)}>{busy ? 'Đang xóa dữ liệu…' : 'Xóa mẫu khuôn mặt của hồ sơ này'}</button>
      </form>
    </> : !error && <p role="status">Đang đọc trạng thái dữ liệu…</p>}
  </section>;
}
