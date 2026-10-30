import { useEffect, useState } from 'react';
import type { PartnerWorker } from './partnerFlow';

export function PartnerAdmissionPanel({batches,onUnauthorized}:{batches:{id:string;name:string}[];onUnauthorized:()=>void}){
  const [batch,setBatch]=useState(''),[workers,setWorkers]=useState<PartnerWorker[]>([]),[page,setPage]=useState(0),[more,setMore]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{if(!batches.some(value=>value.id===batch)){setBatch(batches[0]?.id||'');setPage(0);}},[batches,batch]);
  useEffect(()=>{
    if(!batch){setWorkers([]);return;}
    let active=true,loading=false;const controller=new AbortController();
    async function load(){
      if(loading)return;loading=true;
      try{
        const response=await fetch(`/api/admin/partners/batches/${batch}/workers?offset=${page*50}`,{signal:controller.signal});
        const result=await response.json();if(!active)return;
        if(response.status===401)onUnauthorized();
        if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Chưa tải được danh sách tiếp nhận.');
        setWorkers(result.items);setMore(result.has_more);setError('');
      }catch(e){if(active)setError(e instanceof Error?e.message:'Chưa tải được danh sách.');}
      finally{loading=false;}
    }
    void load();const timer=setInterval(()=>void load(),3000);
    return()=>{active=false;controller.abort();clearInterval(timer);};
  },[batch,page]);
  return <div className="partner-card"><h2>Theo dõi tiếp nhận tự động</h2><p>Người mới xác nhận họ tên tại kiosk, giữ mặt trước camera để hệ thống tự ghi Vào. Không cần quản trị duyệt từng người.</p><label>Đợt / ca<select value={batch} onChange={event=>{setBatch(event.target.value);setPage(0);setWorkers([]);}}><option value="">Chọn đợt</option>{batches.map(value=><option key={value.id} value={value.id}>{value.name}</option>)}</select></label>{error&&<p className="error" role="alert">{error}</p>}<div className="admin-table-wrap"><table><thead><tr><th>Mã tạm</th><th>Họ tên</th><th>Trạng thái</th></tr></thead><tbody>{workers.map(worker=><tr key={worker.id}><td>{worker.code}</td><td>{worker.name||'Đang đọc / nhập tên'}</td><td>{worker.state==='expired'?'Hết phiên':worker.state==='cancelled'?'Đã hủy':worker.state==='active'?'Đã Vào':worker.state==='completed'?'Đã Ra':worker.name_confirmed?'Đang hoàn tất Vào tự động':'Chờ họ tên'}</td></tr>)}{!workers.length&&<tr><td colSpan={3}>Chưa có người được tiếp nhận trong đợt / trang này.</td></tr>}</tbody></table></div><div className="form-actions"><button className="text-button" disabled={page===0} onClick={()=>setPage(value=>value-1)}>← Trang trước</button><span>Trang {page+1}</span><button className="text-button" disabled={!more} onClick={()=>setPage(value=>value+1)}>Trang tiếp →</button></div></div>;
}
