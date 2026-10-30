import { useEffect, useState } from 'react';

type Pending = {request_id:string;employee_code:string;employee_name:string;device_name:string;direction:string;expires_at:string};
export function RecognitionReview({csrf,onUnauthorized}:{csrf:string;onUnauthorized:()=>void}) {
  const [items,setItems]=useState<Pending[]>([]),[selected,setSelected]=useState<Pending|null>(null);
  const [reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[success,setSuccess]=useState('');
  const [pollError,setPollError]=useState('');
  useEffect(()=>{
    let disposed=false,inFlight=false;let active:AbortController|null=null;
    async function load(){
      if(inFlight||disposed)return;inFlight=true;
      const abort=new AbortController();active=abort;const timeout=setTimeout(()=>abort.abort(),10000);
      try{
        const response=await fetch('/api/admin/recognition/pending',{signal:abort.signal});
        if(response.status===401)onUnauthorized();
        const body=await response.json();
        if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Chưa tải được phiên chờ đối chiếu.');
        if(!disposed){setItems(body.items);setPollError('');}
      }catch(error){if(!disposed)setPollError(error instanceof Error?error.message:'Chưa kết nối được máy chủ.');}
      finally{clearTimeout(timeout);inFlight=false;if(active===abort)active=null;}
    }
    void load();const timer=setInterval(()=>void load(),1000);
    return()=>{disposed=true;active?.abort();clearInterval(timer);};
  },[]);
  async function confirm(){
    if(!selected)return;
    setBusy(true);setError('');setSuccess('');
    try{
      const response=await fetch(`/api/admin/recognition/sessions/${selected.request_id}/confirm`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({confirm_employee_code:selected.employee_code,reason}),signal:AbortSignal.timeout(15000)});
      if(response.status===401)onUnauthorized();
      const body=await response.json();
      if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Chưa xác nhận được người tại kiosk.');
      setSelected(null);setReason('');setSuccess('Đã xác nhận đúng người. Kiosk sẽ gửi ghi công và chỉ báo thành công khi nhận biên nhận từ máy chủ.');
    }catch(error){setError(error instanceof Error?error.message:'Chưa rõ kết quả đối chiếu. Tải lại trạng thái trước khi thử lại.');}
    finally{setBusy(false);}
  }
  return <section className="recognition-review">
    <h2>Đối chiếu tại kiosk</h2><p className="section-explanation">Chỉ xác nhận khi người đang có mặt đúng với hồ sơ hiển thị. Các phiên dưới đây đã đạt chuỗi ảnh nhưng chưa được ghi công; phiên tự hết hạn nếu không kịp đối chiếu.</p>
    {(error||pollError)&&<p className="error" role="alert">{error||pollError}</p>}{success&&<p className="success" role="status">{success}</p>}
    <div className="employee-table"><table><thead><tr><th>Hồ sơ máy chủ gợi ý</th><th>Kiosk / chiều</th><th>Thao tác</th></tr></thead><tbody>{items.map(item=><tr key={item.request_id}><td>{item.employee_code} · {item.employee_name}</td><td>{item.device_name} · {item.direction==='in'?'Vào':'Ra'}</td><td><button className="text-button" disabled={busy} onClick={()=>{setSelected(item);setReason('');setError('');setSuccess('');}}>Đối chiếu người này</button></td></tr>)}{!items.length&&<tr><td colSpan={3}>Chưa có phiên còn hạn chờ đối chiếu. Cấu hình ghi công hiện tại có thể chưa được bật.</td></tr>}</tbody></table></div>
    {selected&&<form onSubmit={event=>{event.preventDefault();void confirm();}}><h3>{selected.employee_code} · {selected.employee_name}</h3><p className="section-explanation">{selected.device_name} · {selected.direction==='in'?'Vào':'Ra'}. Xác nhận này không tự thay hồ sơ mà máy chủ đã chọn.</p><label>Lý do đối chiếu<input value={reason} onChange={event=>setReason(event.target.value)} minLength={5} maxLength={500} required disabled={busy}/></label><div className="time-actions"><button type="button" className="text-button" disabled={busy} onClick={()=>setSelected(null)}>Bỏ qua</button><button disabled={busy||reason.trim().length<5}>{busy?'Đang xác nhận…':'Xác nhận đúng người'}</button></div></form>}
  </section>;
}
