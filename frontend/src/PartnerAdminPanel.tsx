import { useEffect, useState, type FormEvent } from 'react';
import './partner.css';
import { PartnerAdmissionPanel } from './PartnerAdmissionPanel';
import { PartnerReportsPanel } from './PartnerReportsPanel';

type Vendor = {id:string;code:string;name:string;active:boolean};
type Batch = {id:string;partner_id:string;name:string;site:string;work_date:string;state:string;capacity:number;starts_at:string;ends_at:string;timezone:string;retention_hours:number;threshold:number|null};
type Device = {id:string;name:string;active:boolean;direction:string};
type Binding = {device_id:string;batch_id:string;active:boolean};
const labels:Record<string,string> = {draft:'Nháp',open:'Đang tiếp nhận',running:'Đang thực hiện',review:'Chờ đối soát',closed:'Đã chốt'};
const transitions:Record<string,{state:string;title:string}[]> = {
  draft:[{state:'open',title:'Mở tiếp nhận'}],
  open:[{state:'running',title:'Dừng nhận người mới'},{state:'review',title:'Chuyển đối soát'}],
  running:[{state:'review',title:'Chuyển đối soát'}],review:[],closed:[],
};
const today=()=>new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Ho_Chi_Minh'});

export function PartnerAdminPanel({csrf,onUnauthorized}:{csrf:string;onUnauthorized:()=>void}) {
  const [vendors,setVendors]=useState<Vendor[]>([]),[batches,setBatches]=useState<Batch[]>([]);
  const [devices,setDevices]=useState<Device[]>([]),[bindings,setBindings]=useState<Binding[]>([]);
  const [day,setDay]=useState(today),[refresh,setRefresh]=useState(0),[busy,setBusy]=useState(false);
  const [error,setError]=useState(''),[message,setMessage]=useState(''),[reason,setReason]=useState('');
  const [vendor,setVendor]=useState({code:'',name:''});
  const [draft,setDraft]=useState({request_id:crypto.randomUUID(),partner_id:'',work_date:today(),name:'Ca tăng cường',site:'',start:'08:00',end:'17:00',capacity:30,requested_count:30});
  const [pause,setPause]=useState({enabled:false,start:'12:00',end:'13:00',paid:false});
  const [binding,setBinding]=useState({device_id:'',batch_id:''});
  const [capacities,setCapacities]=useState<Record<string,number>>({});
  const [more,setMore]=useState(false);
  const [page,setPage]=useState(0);
  async function request(path:string,options:RequestInit={}) {
    const response=await fetch('/api/admin/'+path,{...options,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...options.headers}});
    const body=await response.json();
    if(response.status===401)onUnauthorized();
    if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Dữ liệu chưa hợp lệ. Kiểm tra các trường và thử lại.');
    return body;
  }
  useEffect(()=>{
    const controller=new AbortController();
    Promise.all([
      request('partners',{signal:controller.signal}),
      request(`partners/batches/list?date_from=${day}&date_to=${day}&offset=${page*50}`,{signal:controller.signal}),
      request('devices',{signal:controller.signal}),
      request('partners/devices/list',{signal:controller.signal}),
    ]).then(([vs,bs,ds,links])=>{
      if(controller.signal.aborted)return;
      setVendors(vs.items);setBatches(bs.items);setMore(bs.has_more);setDevices(ds.items);setBindings(links.items);
      setDraft(value=>({...value,partner_id:value.partner_id||vs.items.find((v:Vendor)=>v.active)?.id||''}));
    }).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Chưa tải được dữ liệu đối tác.');});
    return()=>controller.abort();
  },[day,page,refresh,csrf]);
  async function perform(action:()=>Promise<void>) {
    if(busy)return;setBusy(true);setError('');setMessage('');
    try {await action();setRefresh(value=>value+1);}catch(e){setError(e instanceof Error?e.message:'Chưa lưu được dữ liệu.');}
    finally {setBusy(false);}
  }
  function createVendor(event:FormEvent) {
    event.preventDefault();void perform(async()=>{
      const saved=await request('partners',{method:'POST',body:JSON.stringify(vendor)});
      setDraft(value=>({...value,partner_id:saved.id}));setVendor({code:'',name:''});setMessage('Đã tạo đối tác.');
    });
  }
  function createBatch(event:FormEvent) {
    event.preventDefault();void perform(async()=>{
      await request('partners/batches',{method:'POST',body:JSON.stringify({...draft,breaks:pause.enabled?[{start:pause.start,end:pause.end,paid:pause.paid}]:[]})});
      setDay(draft.work_date);setPage(0);setDraft(value=>({...value,request_id:crypto.randomUUID()}));setMessage('Đã tạo đợt nháp. Mở tiếp nhận sau khi kiểm tra cấu hình.');
    });
  }
  function bindDevice(event:FormEvent) {
    event.preventDefault();void perform(async()=>{
      await request('partners/devices/'+binding.device_id,{method:'PUT',body:JSON.stringify({batch_id:binding.batch_id,reason})});
      setMessage('Đã gán thiết bị cho đợt đối tác.');
    });
  }
  return <section className="partner-admin">
    <p className="section-explanation">Lao động thời vụ có mã và mẫu mặt tạm theo ca, tách khỏi Nhân viên công ty. Mẫu tạm hết hạn sau 48 giờ kể từ kết thúc ca; bảng công được giữ riêng.</p>
    <p className="partner-stage-note">Người mới xác nhận họ tên, hệ thống kiểm tra lại đúng khuôn mặt rồi tự động ghi Vào. Gán thiết bị cho đợt, sau đó mở màn hình Chấm công đối tác; không cần duyệt từng người.</p>
    {error&&<p className="error" role="alert">{error}</p>}{message&&<p className="success" role="status">{message}</p>}
    <div className="partner-setup-grid">
      <form onSubmit={createVendor} className="partner-card"><h2>Đối tác cung cấp</h2>
        <label>Mã đối tác<input required maxLength={32} pattern="[A-Za-z0-9_-]+" value={vendor.code} onChange={e=>setVendor({...vendor,code:e.target.value})}/></label>
        <label>Tên đối tác<input required minLength={2} maxLength={160} value={vendor.name} onChange={e=>setVendor({...vendor,name:e.target.value})}/></label>
        <button className="primary-pill-btn" disabled={busy}>Thêm đối tác</button>
        <ul className="partner-vendor-list">{vendors.map(v=><li key={v.id}><strong>{v.code}</strong> · {v.name}{!v.active?' · Đã ngừng':''}</li>)}</ul>
      </form>
      <form onSubmit={createBatch} className="partner-card"><h2>Đợt / ca tăng cường</h2>
        <label>Đối tác<select required value={draft.partner_id} onChange={e=>setDraft({...draft,partner_id:e.target.value})}><option value="">Chọn đối tác</option>{vendors.filter(v=>v.active).map(v=><option key={v.id} value={v.id}>{v.code} · {v.name}</option>)}</select></label>
        <label>Tên đợt / ca<input required minLength={2} maxLength={100} value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></label>
        <label>Sàn / vị trí<input required minLength={2} maxLength={120} value={draft.site} onChange={e=>setDraft({...draft,site:e.target.value})}/></label>
        <div className="partner-input-row"><label>Ngày bắt đầu ca<input required type="date" value={draft.work_date} onChange={e=>setDraft({...draft,work_date:e.target.value})}/></label><label>Số lao động yêu cầu<input required type="number" min={1} max={5000} value={draft.requested_count} onChange={e=>setDraft({...draft,requested_count:Number(e.target.value)})}/></label><label>Hạn mức được tiếp nhận<input required type="number" min={1} max={5000} value={draft.capacity} onChange={e=>setDraft({...draft,capacity:Number(e.target.value)})}/></label></div>
        <div className="partner-input-row"><label>Giờ bắt đầu<input required type="time" value={draft.start} onChange={e=>setDraft({...draft,start:e.target.value})}/></label><label>Giờ kết thúc<input required type="time" value={draft.end} onChange={e=>setDraft({...draft,end:e.target.value})}/></label></div>
        <p>Giờ kết thúc trước giờ bắt đầu là ca qua đêm.</p><label className="partner-check"><input type="checkbox" checked={pause.enabled} onChange={e=>setPause({...pause,enabled:e.target.checked})}/>Có nghỉ giữa ca</label>{pause.enabled&&<><div className="partner-input-row"><label>Bắt đầu nghỉ<input required type="time" value={pause.start} onChange={e=>setPause({...pause,start:e.target.value})}/></label><label>Kết thúc nghỉ<input required type="time" value={pause.end} onChange={e=>setPause({...pause,end:e.target.value})}/></label></div><label className="partner-check"><input type="checkbox" checked={pause.paid} onChange={e=>setPause({...pause,paid:e.target.checked})}/>Khoảng nghỉ vẫn tính công</label></>}
        <button className="primary-pill-btn" disabled={busy||!draft.partner_id}>Tạo đợt nháp</button>
      </form>
    </div>
    <div className="partner-card"><h2>Quản lý đợt và thiết bị</h2>
      <p>Dừng nhận người mới vẫn cho người đã Vào quét Ra. Chuyển đối soát sẽ dừng ghi Vào/Ra để kiểm tra, điều chỉnh và chốt đợt.</p>
      <label>Ngày công cần xem<input type="date" required value={day} onChange={e=>{if(e.target.value){setDay(e.target.value);setPage(0);}}}/></label>
      <label>Lý do thao tác trạng thái / hạn mức / thiết bị<input minLength={5} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)} placeholder="Nhập lý do trước khi thực hiện"/></label>
      <div className="employee-table"><table><thead><tr><th>Đợt / đối tác</th><th>Thời gian</th><th>Trạng thái</th><th>Hạn mức</th><th>Thao tác</th></tr></thead><tbody>{batches.map(batch=><tr key={batch.id}>
        <td><strong>{batch.name}</strong><div>{vendors.find(v=>v.id===batch.partner_id)?.code} · {batch.site}</div></td>
        <td>{new Date(batch.starts_at).toLocaleString('vi-VN',{timeZone:batch.timezone})}<br/>{new Date(batch.ends_at).toLocaleString('vi-VN',{timeZone:batch.timezone})}</td>
        <td>{labels[batch.state]}<small className="partner-policy-note">{batch.threshold===null?'Chưa ghim cấu hình nhận diện':'Đã ghim ngưỡng vận hành hiện có'}</small></td>
        <td><input aria-label={`Hạn mức ${batch.name}`} type="number" min={1} max={5000} value={capacities[batch.id]??batch.capacity} onChange={e=>setCapacities({...capacities,[batch.id]:Number(e.target.value)})}/><button className="text-button" disabled={busy||reason.trim().length<5||['review','closed'].includes(batch.state)} onClick={()=>void perform(async()=>{await request(`partners/batches/${batch.id}/capacity`,{method:'POST',body:JSON.stringify({expected_capacity:batch.capacity,capacity:capacities[batch.id]??batch.capacity,reason})});setMessage('Đã cập nhật hạn mức.');})}>Lưu hạn mức</button></td>
        <td>{transitions[batch.state]?.map(action=><button key={action.state} className="text-button" disabled={busy||reason.trim().length<5} onClick={()=>void perform(async()=>{await request(`partners/batches/${batch.id}/state`,{method:'POST',body:JSON.stringify({expected_state:batch.state,state:action.state,reason})});setMessage('Đã cập nhật trạng thái đợt.');})}>{action.title}</button>)}</td>
      </tr>)}{!batches.length&&<tr><td colSpan={5}>Chưa có đợt trong ngày đã chọn.</td></tr>}</tbody></table></div>
      <div className="form-actions"><button className="text-button" disabled={busy||page===0} onClick={()=>setPage(value=>value-1)}>← Trang trước</button><span>Trang {page+1}</span><button className="text-button" disabled={busy||!more} onClick={()=>setPage(value=>value+1)}>Trang tiếp →</button></div>
      <form onSubmit={bindDevice} className="partner-binding-form"><h3>Gán thiết bị</h3>
        <label>Thiết bị<select required value={binding.device_id} onChange={e=>setBinding({...binding,device_id:e.target.value})}><option value="">Chọn thiết bị</option>{devices.filter(d=>d.active).map(d=><option key={d.id} value={d.id}>{d.name} · {d.direction==='in'?'Vào':'Ra'}</option>)}</select></label>
        <label>Đợt / ca<select required value={binding.batch_id} onChange={e=>setBinding({...binding,batch_id:e.target.value})}><option value="">Chọn đợt</option>{batches.filter(b=>!['review','closed'].includes(b.state)).map(b=><option key={b.id} value={b.id}>{b.name} · {vendors.find(v=>v.id===b.partner_id)?.code}</option>)}</select></label>
        <button className="secondary" disabled={busy||reason.trim().length<5}>Gán cho đợt đối tác</button>
      </form>
      <ul>{bindings.filter(link=>link.active).map(link=><li key={link.device_id}>{devices.find(d=>d.id===link.device_id)?.name||'Thiết bị'} → {batches.find(b=>b.id===link.batch_id)?.name||'Đợt ngoài ngày đang xem'} <button className="text-button" disabled={busy||reason.trim().length<5} onClick={()=>void perform(async()=>{await request(`partners/devices/${link.device_id}/unbind`,{method:'POST',body:JSON.stringify({reason})});setMessage('Đã bỏ gán thiết bị đối tác.');})}>Bỏ gán</button></li>)}</ul>
    </div>
    <PartnerAdmissionPanel batches={batches} onUnauthorized={onUnauthorized}/>
    <PartnerReportsPanel vendors={vendors} csrf={csrf} onUnauthorized={onUnauthorized} refreshKey={refresh} onClosed={()=>setRefresh(value=>value+1)}/>
  </section>;
}
