import { useEffect, useRef, useState, type FormEvent } from 'react';
import './operations.css';

type Status = {
  checked_at: string; database_ok: boolean; recognition_ready: boolean; experimental_pad_ready: boolean;
  attendance_enabled: boolean; attendance_mode: string | null;
  supervisor: {running: boolean; state: string; restart_count: number};
  disk: {free_bytes: number; total_bytes: number};
  backup: {available: boolean; kind: string | null; encrypted: boolean; checksum_verified: boolean; updated_at: string | null; overdue: boolean};
  alerts: string[];
  recovery_key_preserved: boolean;
};
const labels: Record<string,string> = {
  partner_biometric_cleanup_failed: 'Chưa dọn được kho mẫu mặt đối tác hết hạn. Kiểm tra ổ đĩa/quyền truy cập; không tự khởi tạo lại kho đang có dữ liệu.',
  backup_destination_unavailable: 'Thư mục/ổ backup đã cấu hình hiện chưa truy cập được. Kết nối lại ổ đĩa; bản backup local chưa thay thế bản lưu trên ổ riêng.',
  disk_low: 'Ổ đĩa còn dưới 2 GB. Giải phóng dung lượng trước khi tiếp tục lưu dữ liệu.',
  database_unavailable: 'Chưa kết nối được SQL Server.', recognition_unavailable: 'Model nhận diện chưa sẵn sàng.',
  attendance_disabled: 'Ghi công đang tắt hoặc cấu hình chưa sẵn sàng.', supervisor_stopped: 'Backend chưa chạy bằng bộ giám sát tự phục hồi.',
  backup_missing: 'Chưa có bản sao lưu được ghi nhận.', backup_unverified: 'Bản sao lưu chưa được kiểm tra checksum.',
  backup_unencrypted: 'Bản sao lưu gần nhất chưa được mã hóa.', backup_overdue: 'Bản sao lưu gần nhất đã quá 24 giờ.',
  backup_failed: 'Lần sao lưu gần nhất báo lỗi. Kiểm tra dung lượng, quyền thư mục và kết nối SQL Server.',
  recovery_key_not_preserved: 'Chưa xác nhận bản khóa khôi phục được bảo vệ tại nơi lưu backup. Kiểm tra ổ backup hoặc bảo quản khóa bên dưới.',
};
const time = (value: string) => new Date(value).toLocaleString('vi-VN');
export function OperationsPanel({csrf,onUnauthorized}: {csrf:string;onUnauthorized:()=>void}) {
  const [status,setStatus]=useState<Status|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [keyPassword,setKeyPassword]=useState('');
  const [keyConfirmation,setKeyConfirmation]=useState('');
  const [keyBusy,setKeyBusy]=useState(false);
  const [keyMessage,setKeyMessage]=useState('');
  const [keyError,setKeyError]=useState('');
  const request=useRef<AbortController|null>(null);
  async function load() {
    request.current?.abort();
    const controller=new AbortController();request.current=controller;
    setBusy(true);setError('');
    const timeout=setTimeout(()=>controller.abort(),10000);
    try {
      const response=await fetch('/api/admin/operations/status',{signal:controller.signal});
      if(response.status===401){onUnauthorized();return;}
      if(!response.ok)throw new Error('Chưa đọc được trạng thái. Kiểm tra backend và SQL Server, rồi thử lại.');
      const result=await response.json();
      if(!controller.signal.aborted)setStatus(result);
    } catch(e) {
      if(request.current===controller)setError(e instanceof Error&&e.name!=='AbortError'?e.message:'Máy chủ phản hồi quá lâu. Chưa xác nhận được trạng thái mới.');
    } finally {
      clearTimeout(timeout);
      if(request.current===controller){request.current=null;setBusy(false);}
    }
  }
  async function saveRecoveryKey(event:FormEvent) {
    event.preventDefault();setKeyError('');setKeyMessage('');
    if(keyPassword!==keyConfirmation){setKeyError('Hai lần nhập mật khẩu chưa khớp.');return;}
    setKeyBusy(true);
    try {
      const response=await fetch('/api/admin/operations/recovery-key/export',{method:'POST',
        headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
        body:JSON.stringify({password:keyPassword,confirmation:keyConfirmation}),signal:AbortSignal.timeout(60000)});
      if(response.status===401){onUnauthorized();return;}
      const result=await response.json();
      if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Chưa bảo quản được khóa.');
      setKeyPassword('');setKeyConfirmation('');
      setKeyMessage(`Đã lưu khóa có mật khẩu vào thư mục backup: ${result.filename}. Hãy giữ mật khẩu để dùng khi đổi máy.`);
      void load();
    } catch(e){setKeyError(e instanceof Error?e.message:'Chưa kết nối được máy chủ.');}
    finally{setKeyBusy(false);}
  }
  useEffect(()=>{
    void load();
    const interval=setInterval(()=>{if(!request.current&&document.visibilityState==='visible')void load();},15000);
    return()=>{clearInterval(interval);request.current?.abort();request.current=null;};
  },[]);
  return <section className="operations-panel">
    <div className="operations-heading"><div><h2>Trạng thái vận hành</h2><p className="section-explanation">Kiểm tra local; tự cập nhật mỗi 15 giây khi mở trang. Lỗi camera và quyền âm thanh được hiển thị tại từng kiosk.</p></div><button onClick={()=>void load()} disabled={busy}>{busy?'Đang kiểm tra…':'Kiểm tra lại'}</button></div>
    {error&&<p className="error" role="alert">{error}</p>}
    {status&&<>
      <p className="section-explanation">Lần kiểm tra gần nhất: {time(status.checked_at)}{busy?' · Đang cập nhật…':''}</p>
      <div className="operations-grid">
        <article><h3>SQL Server</h3><strong>{status.database_ok?'Kết nối được':'Chưa kết nối'}</strong></article>
        <article><h3>Nhận diện</h3><strong>{status.recognition_ready?'Model sẵn sàng':'Chưa sẵn sàng'}</strong><p>{status.attendance_enabled?(status.attendance_mode==='functional_trial'?'Đang thử luồng một người':'Đã bật ghi công'):'Chưa bật ghi công'}</p></article>
        <article><h3>Tự phục hồi backend</h3><strong>{status.supervisor.running?'Đang giám sát':'Chưa chạy'}</strong><p>{status.supervisor.restart_count} lần khởi động lại do tiến trình dừng.</p></article>
        <article><h3>Dung lượng ổ đĩa</h3><strong>{(status.disk.free_bytes/1024**3).toLocaleString('vi-VN',{maximumFractionDigits:1})} GB còn trống</strong></article>
        <article><h3>Sao lưu gần nhất</h3><strong>{status.backup.updated_at?time(status.backup.updated_at):'Chưa có'}</strong><p>{status.backup.available?`${status.backup.kind==='pre_migration'?'Trước migration':'Vận hành'} · ${status.backup.encrypted?'Đã mã hóa':'Chưa mã hóa'} · ${status.backup.checksum_verified?'Checksum đạt':'Chưa kiểm tra checksum'}`:'Chưa ghi nhận bản sao lưu.'}</p></article>
      </div>
      {!!status.alerts.length&&<div className="operations-alerts" role="status"><h3>Cần xử lý</h3><ul>{status.alerts.map(code=><li key={code}>{labels[code]||code}</li>)}</ul></div>}
      <form className="operations-key" onSubmit={saveRecoveryKey}>
        <h3>Bảo quản khóa khôi phục</h3>
        <p>{status.recovery_key_preserved?'Đã xác nhận bản khóa được bảo vệ trong thư mục backup. Có thể lưu thêm một bản với mật khẩu mới.':'Lưu thêm khóa được bảo vệ bằng mật khẩu để đọc backup khi máy nguồn hỏng.'} Mật khẩu chỉ nhập tại trang này, không gửi qua chat và không được lưu trên máy chủ.</p>
        <div className="operations-key-inputs"><label>Mật khẩu khôi phục<input type="password" autoComplete="new-password" minLength={12} maxLength={512} value={keyPassword} onChange={event=>setKeyPassword(event.target.value)} required disabled={keyBusy}/></label><label>Nhập lại mật khẩu<input type="password" autoComplete="new-password" minLength={12} maxLength={512} value={keyConfirmation} onChange={event=>setKeyConfirmation(event.target.value)} required disabled={keyBusy}/></label></div>
        <p className="section-explanation">Chọn mật khẩu riêng từ 12 ký tự và bảo quản an toàn. Tệp khóa có mật khẩu sẽ được lưu vào thư mục backup đã cấu hình; khóa gốc trên máy không thay đổi.</p>
        <button disabled={keyBusy}>{keyBusy?'Đang mã hóa và lưu…':'Lưu khóa khôi phục có mật khẩu'}</button>
        {keyError&&<p className="error" role="alert">{keyError}</p>}{keyMessage&&<p className="success" role="status">{keyMessage}</p>}
      </form>
      {status.attendance_mode==='functional_trial'&&<p className="section-explanation">Bản thử chức năng một người. Chống ảnh giả và độ chính xác theo nhóm được kiểm chứng trong đợt mở rộng sau.</p>}
    </>}
  </section>;
}
