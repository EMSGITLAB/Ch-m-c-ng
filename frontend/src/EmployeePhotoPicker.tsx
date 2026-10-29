import { useEffect, useRef, useState } from 'react';
import { fullFramePhoto } from './cameraCapture';

export function EmployeePhotoPicker({ current, selected, disabled, onChange }: {
  current?: string | null; selected: Blob | null; disabled: boolean; onChange: (photo: Blob | null) => void;
}) {
  const video = useRef<HTMLVideoElement>(null), stream = useRef<MediaStream | null>(null);
  const generation = useRef(0);
  const [camera, setCamera] = useState(false), [opening, setOpening] = useState(false);
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    if (!selected) { setPreview(''); return; }
    const url = URL.createObjectURL(selected); setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [selected]);
  function stop() {
    generation.current++; stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
    if (video.current) video.current.srcObject = null;
    setCamera(false); setOpening(false);
  }
  useEffect(() => () => { generation.current++; stream.current?.getTracks().forEach(track => track.stop()); }, []);
  async function open() {
    const attempt = ++generation.current; setOpening(true); setError('');
    try {
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      if (attempt !== generation.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media; setCamera(true);
      if (video.current) { video.current.srcObject = media; await video.current.play(); }
    } catch { if (attempt === generation.current) { stop(); setError('Không mở được camera. Kiểm tra quyền camera hoặc tải ảnh từ máy.'); } }
    finally { if (attempt === generation.current) setOpening(false); }
  }
  function choose(photo: Blob) {
    if (photo.size > 2_000_000) { setError('Ảnh tối đa 2 MB.'); return; }
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(photo.type)) { setError('Chọn ảnh JPEG, PNG hoặc WebP.'); return; }
    onChange(photo); setError(''); stop();
  }
  return <fieldset className="employee-photo-picker" disabled={disabled}>
    <legend>Ảnh hồ sơ & mẫu nhận diện</legend>
    <div className="employee-photo-preview">
      <video ref={video} muted playsInline autoPlay hidden={!camera} aria-label="Camera chụp ảnh hồ sơ" />
      {!camera && (preview || current ? <img src={preview || current!} alt="Ảnh hồ sơ nhân viên" /> : <span>Chưa có ảnh</span>)}
    </div>
    <p>Nhìn thẳng, đủ sáng và chỉ có một khuôn mặt. Một ảnh đạt kiểm tra là đủ để làm mẫu nhận diện.</p>
    <div className="employee-photo-actions">
      <label className="photo-file-label">Tải ảnh<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e => { const file = e.target.files?.[0]; if (file) choose(file); e.target.value = ''; }} /></label>
      {!camera ? <button type="button" className="secondary" disabled={opening} onClick={() => void open()}>{opening ? 'Đang mở…' : 'Mở camera'}</button> : <>
        <button type="button" onClick={() => void (async () => { try { if (video.current) choose(await fullFramePhoto(video.current, 1280)); } catch { setError('Camera chưa sẵn sàng; chờ thấy hình rồi chụp lại.'); } })()}>Chụp ảnh hồ sơ</button>
        <button type="button" className="secondary" onClick={stop}>Tắt camera</button></>}
      {selected && <button type="button" className="text-button" onClick={() => { onChange(null); }}>Bỏ ảnh vừa chọn</button>}
    </div>
    {selected && <p role="status">Đã chọn ảnh. Bấm “Lưu hồ sơ” để kiểm tra khuôn mặt và lưu mẫu.</p>}
    {error && <p className="error" role="alert">{error}</p>}
  </fieldset>;
}
