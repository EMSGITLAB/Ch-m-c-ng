import { useEffect, useRef, useState } from 'react';
import { CameraFaceFrame, FacePoseGuide, poseLabels, type Pose } from './FacePoseGuide';
import { cameraPhoto } from './cameraCapture';

type Instruction = { position: number; pose: Pose; title: string; text: string; arrow: string };
type Collection = { id: string; purpose: string; status: string; sample_count: number; expires_at: string; created_at: string; operational_enrollment: boolean; guidance_protocol: string | null; next_instruction: Instruction | null };
const purposeNames: Record<string, string> = { enrollment: 'Mẫu đăng ký', calibration: 'Mẫu hiệu chỉnh', evaluation: 'Mẫu kiểm tra cuối' };
const qualityMessages: Record<string, string> = { no_face: 'Chưa thấy khuôn mặt.', multiple_faces: 'Chỉ một người đứng trước camera.', face_too_small: 'Đứng gần camera hơn một chút.', face_clipped: 'Căn khuôn mặt vào giữa ảnh.', too_dark: 'Tăng ánh sáng phía trước.', too_bright: 'Ảnh quá sáng, tránh nguồn sáng chiếu trực tiếp.', blurred: 'Giữ yên để ảnh rõ hơn.', look_straight: 'Nhìn thẳng và giữ đầu ngay ngắn.', invalid_landmarks: 'Chưa thấy rõ các điểm trên khuôn mặt.' };

export function FaceCollectionPanel({ employee, csrf, onClose, onUnauthorized, initialPurpose = 'enrollment' }: { employee: { id: string; name: string; code: string }; csrf: string; onClose: () => void; onUnauthorized: () => void; initialPurpose?:'enrollment'|'calibration'|'evaluation' }) {
  const [purpose, setPurpose] = useState<string>(initialPurpose);
  const [items, setItems] = useState<Collection[]>([]);
  const [session, setSession] = useState<Collection | null>(null);
  const [camera, setCamera] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [previewPose, setPreviewPose] = useState<Pose>('front');
  const [autoCapture, setAutoCapture] = useState(true);
  const [scanHint, setScanHint] = useState('Đang khởi động rà soát camera…');
  const [stableFrames, setStableFrames] = useState(0);
  const captureInFlight = useRef(false);
  const video = useRef<HTMLVideoElement>(null);
  const media = useRef<MediaStream | null>(null);
  const sequence = useRef(0);

  async function request(url: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers); headers.set('X-CSRF-Token', csrf);
    const response = await fetch(url, { ...options, headers, signal: options.signal || AbortSignal.timeout(20000) });
    let body;
    try { body = await response.json(); }
    catch { throw new Error('Chưa kết nối được máy chủ local. Vui lòng thử lại sau vài giây.'); }
    if (!response.ok) {
      if (response.status === 401) onUnauthorized();
      if (body.feedback) throw new Error(body.feedback);
      if (body.reason) throw new Error(qualityMessages[body.reason] || 'Ảnh chưa đủ chất lượng.');
      throw new Error(typeof body.detail === 'string' ? body.detail : 'Không xử lý được yêu cầu.');
    }
    return body;
  }

  useEffect(() => {
    const controller = new AbortController();
    request(`/api/admin/employees/${employee.id}/collections`, { signal: controller.signal }).then(body => { if (!controller.signal.aborted) setItems(body.items); }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [employee.id, refresh]);
  useEffect(() => () => { sequence.current++; media.current?.getTracks().forEach(track => track.stop()); }, []);

  useEffect(() => {
    const collection = session;
    if (!camera || !collection?.next_instruction || !autoCapture) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let pending: AbortController | null = null;
    setStableFrames(0); setScanHint('Đặt mặt trong khung và làm theo tư thế mẫu.');
    async function scan() {
      if (disposed) return;
      if (!captureInFlight.current && video.current?.videoWidth) {
        let deadline: ReturnType<typeof setTimeout> | undefined;
        try {
          const photo = await cameraPhoto(video.current);
          if (disposed) return;
          pending = new AbortController(); deadline = setTimeout(() => pending?.abort(), 8000);
          const response = await fetch(`/api/admin/collections/${collection!.id}/preview`, { method: 'POST', headers: { 'Content-Type': 'image/jpeg', 'X-CSRF-Token': csrf }, body: photo, signal: pending.signal });
          const body = await response.json();
          clearTimeout(deadline); pending = null;
          if (disposed) return;
          if (response.status === 401) { onUnauthorized(); return; }
          if ([403, 404, 409].includes(response.status)) { setAutoCapture(false); setError(typeof body.detail === 'string' ? body.detail : 'Phiên chụp đã thay đổi. Hãy mở lại phiên.'); return; }
          if (!response.ok) { setStableFrames(0); setScanHint('Máy chủ đang bận. Camera sẽ rà soát lại…'); }
          else {
            if (body.collection && body.collection.sample_count !== collection!.sample_count) { setSession(body.collection); return; }
            setStableFrames(body.stable_frames || 0); setScanHint(body.feedback);
            if (body.ready && body.capture_token && !captureInFlight.current) await savePhoto(photo, body.capture_token);
          }
        } catch {
          if (!disposed) { setStableFrames(0); setScanHint('Đang chờ kết nối máy chủ local. Sẽ tự thử lại…'); }
        } finally { clearTimeout(deadline); pending = null; }
      }
      if (!disposed) timer = setTimeout(scan, 500);
    }
    timer = setTimeout(scan, 900);
    return () => { disposed = true; clearTimeout(timer); pending?.abort(); };
  }, [camera, session?.id, session?.sample_count, autoCapture, csrf]);

  function stopCamera() {
    sequence.current++; media.current?.getTracks().forEach(track => track.stop()); media.current = null;
    if (video.current) video.current.srcObject = null;
    setCamera(false);
  }

  async function openCamera() {
    const current = ++sequence.current;
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera cần localhost hoặc HTTPS tin cậy.');
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
    if (current !== sequence.current || !video.current) { stream.getTracks().forEach(track => track.stop()); return; }
    media.current = stream; video.current.srcObject = stream;
    try { await video.current.play(); if (current === sequence.current) setCamera(true); else stream.getTracks().forEach(track => track.stop()); }
    catch (e) { stream.getTracks().forEach(track => track.stop()); throw e; }
  }

  async function begin(existing?: Collection) {
    setBusy(true); setError(''); setSuccess('');
    try {
      const created = existing || await request(`/api/admin/employees/${employee.id}/collections`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ purpose }) });
      setSession(created); setAutoCapture(true); setRefresh(value => value + 1); await openCamera();
    } catch (e) { setError(e instanceof Error ? e.message : 'Không mở được camera.'); }
    finally { setBusy(false); }
  }

  async function savePhoto(photo: Blob, token?: string) {
    if (!session || captureInFlight.current) return;
    captureInFlight.current = true;
    setBusy(true); setError(''); setSuccess('');
    try {
      const headers: Record<string, string> = { 'Content-Type': 'image/jpeg' };
      if (token) { headers['X-Capture-Mode'] = 'auto'; headers['X-Capture-Token'] = token; }
      const result = await request(`/api/admin/collections/${session.id}/samples`, { method: 'POST', headers, body: photo });
      setSession(result.collection); setRefresh(value => value + 1); setSuccess(result.feedback);
    } catch (e) { setError(e instanceof Error ? `Kết quả lần chụp: ${e.message}` : 'Chưa lưu được mẫu. Hãy thử chụp lại.'); }
    finally { captureInFlight.current = false; setBusy(false); }
  }

  async function takePhoto() {
    if (!video.current?.videoWidth) return;
    try { await savePhoto(await cameraPhoto(video.current)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Không chụp được ảnh.'); }
  }

  async function finish(cancel = false, existing?: Collection) {
    const target = existing || session;
    if (!target) return;
    setAutoCapture(false);
    setBusy(true); setError('');
    try {
      const result = await request(`/api/admin/collections/${target.id}/${cancel ? 'cancel' : 'complete'}`, { method: 'POST' });
      stopCamera(); setSession(null); setRefresh(value => value + 1);
      setSuccess(cancel ? 'Đã hủy phiên và xóa mẫu của phiên đang chụp.' : `Đã lưu bộ ${result.sample_count} mẫu đặc trưng trên máy chủ local. Bộ mẫu đang phục vụ hiệu chỉnh, chưa dùng ghi công.`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Không kết thúc được phiên.'); }
    finally { setBusy(false); }
  }

  return <section className="face-collection-panel">
    <div className="collection-heading"><div><h2>Thu mẫu khuôn mặt</h2><p>{employee.code} · {employee.name}</p></div><button className="text-button" onClick={() => { stopCamera(); onClose(); }} disabled={busy}>Về danh sách</button></div>
    <p className="section-explanation">Chụp lần lượt theo hướng dẫn trước từng ảnh. Mỗi bộ cần ít nhất 5 mẫu đạt; có thể chụp thêm vòng 2 để đủ 10 mẫu. Chỉ vector đặc trưng và chỉ số chất lượng được lưu trong SQL Server local; ảnh gốc không được lưu. Chưa bật nhận diện ghi công.</p>
    {error && <div className="error" role="alert">{error}</div>}
    {success && <p className="success" role="status">{success}</p>}
    <div className="collection-layout"><div className="collection-camera"><video ref={video} muted autoPlay playsInline aria-label="Camera thu mẫu khuôn mặt, hình xem trước dạng gương" />{!camera && <div className="camera-idle-guide"><FacePoseGuide pose={session?.next_instruction?.pose || previewPose} /></div>}<CameraFaceFrame count={session?.sample_count || 0} pose={session?.next_instruction?.pose || (session ? null : previewPose)} active={camera} steady={autoCapture && stableFrames > 0} /></div><div className="collection-controls">
      {!session ? <><div className="pose-preview"><div className="pose-preview-content"><div><h3>Làm quen với tư thế chụp</h3><p>Nhìn khuôn mặt mẫu và làm theo chuyển động. Trái/phải là phía của chính bạn trong hình gương.</p></div></div><div className="pose-preview-options" aria-label="Xem trước tư thế">{(Object.keys(poseLabels) as Pose[]).map(pose => <button key={pose} type="button" aria-pressed={previewPose === pose} onClick={() => setPreviewPose(pose)}>{poseLabels[pose]}</button>)}</div></div><label>Mục đích bộ mẫu<select value={purpose} onChange={e => setPurpose(e.target.value)} disabled={busy}><option value="enrollment">Mẫu đăng ký</option><option value="calibration">Mẫu hiệu chỉnh</option><option value="evaluation">Mẫu kiểm tra cuối</option></select></label><p>Mỗi mục đích cần một phiên chụp riêng. Không dùng lại ảnh của bộ khác; giữ riêng bộ kiểm tra cuối khi chọn ngưỡng.</p><button onClick={() => begin()} disabled={busy}>{busy ? 'Đang mở camera…' : 'Bắt đầu phiên chụp'}</button></> : <>
        <span className="eyebrow">{purposeNames[session.purpose]}</span><strong className="sample-counter">{session.sample_count}<span>/ 10 mẫu đạt</span></strong>
        {session.next_instruction ? <div className="pose-instruction face-pose-instruction" role="status" aria-live="polite"><FacePoseGuide pose={session.next_instruction.pose} /><div><span className="pose-step-label">Mẫu {session.next_instruction.position} · {session.next_instruction.position > 5 ? 'Vòng 2' : 'Vòng 1'}</span><h3>{session.next_instruction.title}</h3><p>{session.next_instruction.text}</p><small>Trái/phải là phía của chính bạn trong hình gương.</small></div></div> : <p>{session.sample_count >= 10 ? 'Đã đủ 10 mẫu đạt. Bấm Hoàn tất bộ mẫu để lưu bộ.' : 'Phiên cũ chưa có hướng dẫn tư thế. Hãy hủy phiên và tạo bộ mới.'}</p>}
        <p>Ảnh được kiểm tra độ rõ, ánh sáng, số khuôn mặt và hướng mặt sơ bộ. Hướng mặt được ước lượng từ các điểm trên mặt, chưa thay thế bước kiểm chứng trên camera thực tế.</p>
        {camera && session.next_instruction && <div className="auto-capture-status"><div><strong>{autoCapture ? 'Đang tự rà soát và chụp' : 'Đã tạm dừng tự chụp'}</strong><button className="text-button" onClick={() => setAutoCapture(value => !value)} disabled={busy}>{autoCapture ? 'Tạm dừng' : 'Bật tự chụp'}</button></div><p role="status">{autoCapture ? scanHint : 'Bạn có thể bật lại tự chụp hoặc chụp thủ công.'}</p>{autoCapture && <div className="capture-stability" aria-label={`${stableFrames}/3 khung hình ổn định`}>{[1, 2, 3].map(step => <span key={step} className={step <= stableFrames ? 'stable' : ''} />)}</div>}</div>}
        <button className={camera && autoCapture ? 'secondary' : ''} onClick={() => camera ? takePhoto() : begin(session)} disabled={busy || !session.next_instruction}>{busy ? 'Đang kiểm tra và lưu ảnh…' : camera ? `Chụp thủ công mẫu ${session.next_instruction?.position}` : 'Mở lại camera'}</button>
        <button className="secondary" onClick={() => finish()} disabled={busy || session.sample_count < 5}>Hoàn tất bộ mẫu</button><button className="text-button danger" onClick={() => finish(true)} disabled={busy}>Hủy bộ mẫu đang chụp</button>
      </>}
    </div></div>
    <h3>Các phiên đã tạo</h3><p className="section-explanation">Phiên camera hết hạn sẽ dừng nhận thêm ảnh. Nếu đã đủ 5 mẫu đạt, bạn vẫn có thể hoàn tất bộ mẫu đã chụp. Ảnh nhập để thử nghiệm được lưu riêng thành bộ 1 mẫu khi đạt bộ lọc.</p><div className="employee-table"><table><thead><tr><th>Mục đích</th><th>Số mẫu</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td>{purposeNames[item.purpose]}<br /><small>{item.guidance_protocol === 'imported-photo-v1' ? 'Ảnh nhập để thử nghiệm · 1 mẫu' : item.guidance_protocol ? 'Có hướng dẫn và kiểm tra tư thế sơ bộ' : 'Bộ cũ: chưa kiểm tra tư thế'}</small></td><td>{item.sample_count}</td><td>{item.status === 'complete' ? 'Bộ mẫu đã lưu' : item.status === 'cancelled' ? 'Đã hủy' : new Date(item.expires_at).getTime() <= Date.now() ? 'Phiên hết hạn' : 'Đang thu mẫu'}</td><td>{item.status === 'open' && new Date(item.expires_at).getTime() > Date.now() && <button className="text-button" onClick={() => begin(item)} disabled={busy || !!session}>Tiếp tục phiên</button>}{item.status === 'open' && item.sample_count >= 5 && <button className="text-button" onClick={() => finish(false, item)} disabled={busy || !!session}>Hoàn tất bộ {item.sample_count} mẫu</button>}</td></tr>)}{!items.length && <tr><td colSpan={4} className="empty-state">Chưa có bộ mẫu.</td></tr>}</tbody></table></div>
  </section>;
}
