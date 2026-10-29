import { useEffect, useState } from 'react';
import { RecognitionReview } from './RecognitionReview';
import { PadTrialPanel } from './PadTrialPanel';
import { CalibrationCoveragePanel } from './CalibrationCoveragePanel';
import './calibration.css';

type Report = {
  status: string; reasons: string[];
  coverage: { enrolled_people: number; enrollment_samples: number; known_probe_people: number; known_probes: number; unknown_probe_people: number; unknown_probes: number; completed_collections: number };
  candidate: null | { threshold: number; minimum_margin: number; correct_samples: number; known_samples: number; single_sample_correct_rate: number };
  same_person_diagnostics?: null | { samples: number; minimum: number; median: number; maximum: number; mean: number };
  reference_experiments?: {reference_cap:number;reference_images_used:number;enrolled_people:number;people_below_reference_cap:number;known_probe_people:number;known_probe_samples:number;known_top1_correct_samples:number;known_expected_person_scores:null|{minimum:number;median:number;maximum:number}}[];
};

export function CalibrationPanel({ csrf, onUnauthorized }: { csrf: string; onUnauthorized: () => void }) {
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [trialEnabled, setTrialEnabled] = useState(false);
  useEffect(()=>{
    const controller=new AbortController();
    void fetch('/api/system/status',{signal:controller.signal}).then(response=>response.json())
      .then(status=>setTrialEnabled(status.attendance_enabled&&status.attendance_mode==='functional_trial'))
      .catch(()=>{});
    return()=>controller.abort();
  },[]);
  const [view,setView]=useState<'recognition'|'pad'|'review'>('recognition');
  async function inspect() {
    setBusy(true); setError(''); setReport(null);
    try {
      const response = await fetch('/api/admin/recognition/calibration', { method: 'POST', headers: { 'X-CSRF-Token': csrf }, signal: AbortSignal.timeout(60000) });
      const body = await response.json();
      if (response.status === 401) onUnauthorized();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Không đánh giá được dữ liệu.');
      setReport(body);
    } catch (e) { setError(e instanceof Error ? e.message : 'Không kết nối được máy chủ.'); }
    finally { setBusy(false); }
  }
  return <section className="calibration-panel">
    <nav className="ai-review-nav" aria-label="Nội dung kiểm chứng AI"><button className={view==='recognition'?'selected':''} onClick={()=>setView('recognition')}>Nhận diện & ngưỡng — T09</button><button className={view==='pad'?'selected':''} onClick={()=>setView('pad')}>Chống giả mạo — T11</button><button className={view==='review'?'selected':''} onClick={()=>setView('review')}>Đối chiếu tại kiosk</button></nav>
    {view==='review'?<RecognitionReview csrf={csrf} onUnauthorized={onUnauthorized}/>:view==='pad'?<PadTrialPanel csrf={csrf} onUnauthorized={onUnauthorized}/>:<>
    <h2>Hiệu chỉnh nhận diện — T09</h2>
    {trialEnabled&&<p className="success">Đã bật thử luồng một người: vào Chấm công để camera tự nhận diện và ghi công. Không cần thêm người hoặc quản trị xác nhận từng lượt.</p>}
    <details><summary>Kiểm chứng theo nhóm — thử mở rộng sau</summary>
    <CalibrationCoveragePanel csrf={csrf} onUnauthorized={onUnauthorized} onChanged={()=>setReport(null)}/>
    <p className="section-explanation">Bộ đăng ký và bộ hiệu chỉnh cần được chụp ở các phiên riêng. Người ngoài danh sách là hồ sơ thử chỉ có bộ hiệu chỉnh, chưa có bộ đăng ký hoàn tất. Chỉ bộ mẫu đã hoàn tất của hồ sơ đang hoạt động được dùng để tính toán.</p>
    <p className="section-explanation">Có thể kiểm tra điểm so khớp bước đầu với một người đã chụp ở hai phiên. Để chọn ngưỡng cho nhóm sử dụng, cần bổ sung nhiều người và người ngoài danh sách theo kế hoạch kiểm chứng. Bộ kiểm tra cuối được giữ riêng.</p>
    <button onClick={inspect} disabled={busy}>{busy ? 'Đang kiểm tra dữ liệu local…' : 'Kiểm tra và đề xuất ngưỡng'}</button>
    {error && <p className="error" role="alert">{error}</p>}
    {report && <div aria-live="polite">
      <h3>{report.status === 'insufficient_data' ? 'Chưa đủ dữ liệu hiệu chỉnh' : report.status === 'no_safe_candidate' ? 'Chưa tìm được ngưỡng đáp ứng tiêu chí' : 'Có ngưỡng đề xuất — cần kiểm chứng độc lập'}</h3>
      <div className="employee-table"><table><thead><tr><th>Nhóm dữ liệu</th><th>Số người</th><th>Số ảnh đạt</th></tr></thead><tbody>
        <tr><td>Đăng ký hoàn tất</td><td>{report.coverage.enrolled_people}</td><td>{report.coverage.enrollment_samples}</td></tr>
        <tr><td>Hiệu chỉnh người đã đăng ký</td><td>{report.coverage.known_probe_people}</td><td>{report.coverage.known_probes}</td></tr>
        <tr><td>Hiệu chỉnh người ngoài danh sách</td><td>{report.coverage.unknown_probe_people}</td><td>{report.coverage.unknown_probes}</td></tr>
      </tbody></table></div>
      {report.same_person_diagnostics && <><h3>So khớp thử cùng người giữa hai phiên</h3><div className="employee-table"><table><thead><tr><th>Số ảnh so sánh</th><th>Điểm thấp nhất</th><th>Trung vị</th><th>Cao nhất</th></tr></thead><tbody><tr><td>{report.same_person_diagnostics.samples}</td><td>{report.same_person_diagnostics.minimum.toFixed(3)}</td><td>{report.same_person_diagnostics.median.toFixed(3)}</td><td>{report.same_person_diagnostics.maximum.toFixed(3)}</td></tr></tbody></table></div><p className="section-explanation">Đây là điểm tương đồng cosine, không phải phần trăm độ chính xác. Chưa có phép đo nhận nhầm người khác hoặc người lạ nếu bộ thử chưa có những nhóm đó.</p></>}
      {!!report.reference_experiments?.length&&<><h3>So sánh giới hạn 1 / 3 / 5 ảnh tham chiếu</h3><div className="employee-table"><table><thead><tr><th>Tối đa ảnh/người</th><th>Số ảnh dùng</th><th>Người chưa đủ số ảnh này</th><th>Ảnh thử mới / số người</th><th>Đúng người ở hạng đầu</th><th>Điểm cùng người thấp nhất / trung vị</th></tr></thead><tbody>{report.reference_experiments.map(item=><tr key={item.reference_cap}><td>{item.reference_cap}</td><td>{item.reference_images_used}</td><td>{item.people_below_reference_cap}</td><td>{item.known_probe_samples} / {item.known_probe_people}</td><td>{item.known_probe_samples?`${item.known_top1_correct_samples}/${item.known_probe_samples}`:'Chưa có ảnh thử mới'}</td><td>{item.known_expected_person_scores?`${item.known_expected_person_scores.minimum.toFixed(3)} / ${item.known_expected_person_scores.median.toFixed(3)}`:'—'}</td></tr>)}</tbody></table></div><p className="section-explanation">Cùng danh sách người và cùng ảnh thử cho cả ba cấu hình; người chưa có đủ 3/5 ảnh dùng số ảnh hiện có. Không nhân bản ảnh và không chọn mẫu theo điểm thử. Xếp hạng đầu chưa phải xác nhận danh tính hoặc tỷ lệ nhận diện của toàn nhóm; chưa chọn ngưỡng vận hành từ bảng này.</p></>}
      {!!report.reasons.length && <ul>{report.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
      {report.candidate && <p className="success">Ngưỡng đề xuất: {report.candidate.threshold.toFixed(2)}; khoảng cách hai ứng viên: {report.candidate.minimum_margin.toFixed(2)}. Nhận đúng {report.candidate.correct_samples}/{report.candidate.known_samples} ảnh hiệu chỉnh. Đây là kết quả từng ảnh trong tập hiện có, chưa phải tỷ lệ phiên chấm công thực tế.</p>}
      <p className="section-explanation">Đây là phép đo theo nhóm, không chặn chế độ thử chức năng một người. Kết quả trong bảng chưa phải nghiệm thu độ chính xác khi mở rộng.</p>
    </div>}
    </details>
    </>}
  </section>;
}
