import { useEffect, useRef, useState } from 'react';
import type { PartnerState, PartnerWorker } from './partnerFlow';
import './partner-name-dialog.css';

type Props={worker:PartnerWorker;phase:PartnerState['phase'];name:string;voice:'idle'|'starting'|'recording'|'processing';busy:boolean;message:string;feedback:string;stream:MediaStream|null;onName:(name:string)=>void;onRead:()=>void;onStopRead:()=>void;onManual:()=>void;onConfirm:()=>void;onCancel:()=>void};
export function PartnerNameDialog(props:Props){
  const {worker,phase,name,voice,busy,message,feedback}=props;
  const dialog=useRef<HTMLDialogElement>(null),input=useRef<HTMLInputElement>(null),micro=useRef<HTMLButtonElement>(null);
  const [mode,setMode]=useState<'voice'|'manual'>('voice');
  const expired=phase==='expired'||worker.state==='expired';
  const verifying=busy||phase==='verifying';
  useEffect(()=>{
    const element=dialog.current;if(!element)return;
    const overflow=document.body.style.overflow;document.body.style.overflow='hidden';
    if(!element.open)element.showModal();
    return()=>{element.close();document.body.style.overflow=overflow;};
  },[]);
  useEffect(()=>{if(!verifying&&!expired)(mode==='manual'?input.current:micro.current)?.focus();},[mode,verifying,expired]);
  return <dialog ref={dialog} className="partner-name-dialog" aria-labelledby="partner-name-title" aria-describedby="partner-name-description" onCancel={event=>{event.preventDefault();props.onCancel();}}>
    <header className="partner-name-header"><span className="partner-name-check" aria-hidden="true">✓</span><div><p>ĐÃ NHẬN DIỆN KHUÔN MẶT</p><strong>Mã tạm <span>{worker.code}</span></strong></div></header>
    <ol className="partner-name-steps" aria-label="Tiến trình tiếp nhận"><li className="done">✓ Khuôn mặt</li><li className={!worker.name_confirmed?'current':'done'}>2. Họ và tên</li><li className={worker.name_confirmed?'current':''}>3. Vào ca</li></ol>
    <div className="partner-name-body">
      <h2 id="partner-name-title">{expired?'Phiên nhập tên đã hết hạn':verifying?'Đang tự động ghi nhận Vào':'Bạn tên là gì?'}</h2>
      <p id="partner-name-description">{expired?'Chưa ghi lượt Vào. Chọn Quét lại để bắt đầu phiên mới.':verifying?'Giữ đúng người vừa quét trước camera. Hệ thống kiểm tra lại mặt và tự động ghi Vào, không cần quản trị duyệt.':'Đọc rõ họ tên hoặc chọn nhập bằng tay. Kiểm tra chữ và dấu trước khi xác nhận.'}</p>
      {!expired&&!verifying&&<>
        <div className="partner-name-tabs" role="tablist" aria-label="Cách khai báo họ tên"><button role="tab" aria-selected={mode==='voice'} onClick={()=>setMode('voice')}>Đọc họ tên</button><button role="tab" aria-selected={mode==='manual'} onClick={()=>{props.onManual();setMode('manual');}}>Nhập bằng tay</button></div>
        {mode==='voice'&&<div className={`partner-voice-step voice-${voice}`}><button ref={micro} type="button" className="partner-micro-button" disabled={voice==='starting'||voice==='processing'} onClick={()=>voice==='recording'?props.onStopRead():props.onRead()} aria-label={voice==='recording'?'Dừng đọc và nhận tên':'Bắt đầu đọc họ tên'}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="8" y="2" width="8" height="13" rx="4"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/></svg></button><strong>{voice==='recording'?'Đang nghe… Bấm micro để gửi ngay':voice==='processing'?'Đang chuyển giọng nói thành tên…':voice==='starting'?'Đang mở micro…':'Bấm micro rồi đọc đầy đủ họ tên'}</strong><span>Tự kết thúc khi nói xong · Tối đa 8 giây · Có thể nhập tay</span></div>}
        <label className="partner-name-input-label" htmlFor="partner-declared-name">{mode==='voice'?'Họ tên nhận được — bạn có thể sửa':'Họ và tên của bạn'}</label><input ref={input} id="partner-declared-name" className="partner-declared-name" autoComplete="off" maxLength={160} value={name} placeholder="Nhập đầy đủ họ và tên" onChange={event=>props.onName(event.target.value)}/>
        {message&&<p className="partner-name-message" role="status">{message}</p>}
      </>}
      {verifying&&!expired&&<div className="partner-name-verification"><video autoPlay playsInline muted ref={element=>{if(element&&element.srcObject!==props.stream){element.srcObject=props.stream;void element.play().catch(()=>{});}}}/><p role="status">{feedback}</p></div>}
    </div>
    <footer className="partner-name-footer">
      {!expired&&!verifying&&<button className="partner-name-confirm" disabled={!name.trim()||voice==='starting'||voice==='processing'} onClick={props.onConfirm}>Xác nhận họ tên <span aria-hidden="true">→</span></button>}
      <button className="partner-name-cancel" onClick={props.onCancel}>{expired?'Quét lại':'Hủy tiếp nhận'}</button>
      <p>Mã tạm được giữ trong phiên này · Giọng nói không được lưu lại.</p>
    </footer>
  </dialog>;
}
