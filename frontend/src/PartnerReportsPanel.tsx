import { useEffect, useState, type FormEvent } from 'react';
import { localDateISO } from './dates';
import { changedReportFields, localDateTimeInput, reportRows, type ReportRow } from './partnerReportView';
import './partner-reports.css';

type Vendor={id:string;name:string;code:string};
type Batch={id:string;partner_id:string;name:string;site:string;work_date:string;state:string;timezone:string};
type Report={source_hash:string;as_of:string;closed:boolean;closed_at?:string;closed_by?:number;close_reason?:string;partner:Vendor;batch:Batch;rows:ReportRow[];summary:{requested:number;capacity:number;admitted:number;complete:number;incomplete:number;pending:number;available_slots:number;total_worked_seconds:number};note:string};
type Edit={row:ReportRow;source:string;requestId:string;name:string;in_local:string;out_local:string;reason:string};
const labels:Record<string,string>={draft:'Nháp',open:'Đang tiếp nhận',running:'Đang thực hiện',review:'Chờ đối soát',closed:'Đã chốt'};
const hours=(seconds:number|null)=>seconds===null?'—':(seconds/3600).toLocaleString('vi-VN',{maximumFractionDigits:2});

export function PartnerReportsPanel({vendors,csrf,onUnauthorized,onClosed,refreshKey=0}:{vendors:Vendor[];csrf:string;onUnauthorized:()=>void;onClosed:()=>void;refreshKey?:number}){
  const [range,setRange]=useState({from:localDateISO(),to:localDateISO(),partner:'',site:''});
  const [batches,setBatches]=useState<Batch[]>([]),[batch,setBatch]=useState(''),[batchPage,setBatchPage]=useState(0),[moreBatches,setMoreBatches]=useState(false);
  const [result,setResult]=useState<Report|null>(null),[filter,setFilter]=useState('all'),[page,setPage]=useState(0);
  const [error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[refresh,setRefresh]=useState(0);
  const [edit,setEdit]=useState<Edit|null>(null),[detail,setDetail]=useState<ReportRow|null>(null);
  const [closeReason,setCloseReason]=useState(''),[ack,setAck]=useState(false),[closeId,setCloseId]=useState(crypto.randomUUID());
  async function api(path:string,options:RequestInit={}){
    const response=await fetch('/api/admin/partners'+path,{...options,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...options.headers},signal:options.signal||AbortSignal.timeout(20000)});
    const body=await response.json();if(response.status===401)onUnauthorized();
    if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Dữ liệu chưa hợp lệ. Kiểm tra ngày/giờ và lý do.');
    return body;
  }
  useEffect(()=>{
    let active=true;const controller=new AbortController();
    const query=new URLSearchParams({date_from:range.from,date_to:range.to,offset:String(batchPage*50)});
    if(range.partner)query.set('partner_id',range.partner);if(range.site)query.set('site',range.site);
    api('/batches/list?'+query,{signal:controller.signal}).then(body=>{if(active){setBatches(body.items);setMoreBatches(body.has_more);setBatch(value=>body.items.some((row:Batch)=>row.id===value)?value:body.items[0]?.id||'');setError('');}}).catch(error=>{if(active)setError(error instanceof Error?error.message:'Chưa tải được đợt.');});
    return()=>{active=false;controller.abort();};
  },[range.from,range.to,range.partner,range.site,batchPage,refresh,refreshKey,csrf]);
  useEffect(()=>{setEdit(null);setDetail(null);setCloseReason('');setAck(false);setCloseId(crypto.randomUUID());setPage(0);setResult(null);},[batch]);
  useEffect(()=>{setBatch('');setBatches([]);setResult(null);setEdit(null);setDetail(null);},[range.from,range.to,range.partner,range.site,batchPage]);
  useEffect(()=>{
    if(!batch)return;
    let active=true;const controller=new AbortController();
    api(`/batches/${batch}/report`,{signal:controller.signal}).then(body=>{if(active){setResult(body);setError('');}}).catch(error=>{if(active){setResult(null);setError(error instanceof Error?error.message:'Chưa tải được báo cáo.');}});
    return()=>{active=false;controller.abort();};
  },[batch,refresh,refreshKey,csrf]);
  async function save(event:FormEvent){
    event.preventDefault();if(!edit||!result||busy)return;
    const changes=changedReportFields(edit.row,edit,result.batch.timezone);if(!Object.keys(changes).length)return;
    setBusy(true);setError('');setMessage('');
    try{
      await api(`/workers/${edit.row.worker_id}/adjustments`,{method:'POST',body:JSON.stringify({request_id:edit.requestId,expected_source:edit.source,reason:edit.reason,...changes})});
      setEdit(null);setDetail(null);setMessage('Đã lưu điều chỉnh; lượt camera gốc được giữ nguyên.');setRefresh(value=>value+1);
    }catch(error){setError(error instanceof Error?error.message:'Chưa rõ kết quả; tải lại bảng/lịch sử trước khi gửi yêu cầu khác.');}
    finally{setBusy(false);}
  }
  async function close(){
    if(!result||busy)return;setBusy(true);setError('');setMessage('');
    try{
      const saved=await api(`/batches/${result.batch.id}/close`,{method:'POST',body:JSON.stringify({request_id:closeId,expected_source:result.source_hash,reason:closeReason,acknowledge_incomplete:ack})});
      setResult(saved);setEdit(null);setMessage('Đã chốt đợt. Bản chốt được giữ riêng và không còn sửa trực tiếp.');onClosed();setRefresh(value=>value+1);
    }catch(error){setError(error instanceof Error?error.message:'Chưa rõ kết quả chốt; tải lại trạng thái trước khi thử lại.');}
    finally{setBusy(false);}
  }
  const rows=result?reportRows(result.rows,filter):[];
  const time=(value:string|null)=>value?new Date(value).toLocaleString('vi-VN',{timeZone:result?.batch.timezone||'Asia/Ho_Chi_Minh',hour12:false}):'—';
  const changes=edit&&result?changedReportFields(edit.row,edit,result.batch.timezone):{};
  return <div className="partner-card partner-reports">
    <h2>Theo dõi và đối soát</h2><p>Lọc ngày/đối tác/sàn, chọn đợt để kiểm tra từng mã lao động. “Chưa ghi lượt Ra” không khẳng định người vẫn hiện diện tại sàn.</p>
    <div className="partner-report-filters">
      <label>Từ ngày<input type="date" value={range.from} disabled={busy} onChange={event=>{setRange({...range,from:event.target.value});setBatchPage(0);}}/></label>
      <label>Đến ngày<input type="date" value={range.to} disabled={busy} onChange={event=>{setRange({...range,to:event.target.value});setBatchPage(0);}}/></label>
      <label>Đối tác<select value={range.partner} disabled={busy} onChange={event=>{setRange({...range,partner:event.target.value});setBatchPage(0);}}><option value="">Tất cả đối tác</option>{vendors.map(vendor=><option key={vendor.id} value={vendor.id}>{vendor.code} · {vendor.name}</option>)}</select></label>
      <label>Sàn / vị trí cần tìm<input maxLength={120} value={range.site} disabled={busy} onChange={event=>{setRange({...range,site:event.target.value});setBatchPage(0);}}/></label>
      <label>Đợt / ca đối soát<select value={batch} disabled={busy} onChange={event=>setBatch(event.target.value)}><option value="">Chọn đợt</option>{batches.map(row=><option key={row.id} value={row.id}>{row.work_date} · {row.name} · {row.site} · {labels[row.state]}</option>)}</select></label>
    </div>
    <div className="form-actions"><button className="text-button" disabled={busy||batchPage===0} onClick={()=>setBatchPage(value=>value-1)}>← Đợt trang trước</button><span>Trang đợt {batchPage+1}</span><button className="text-button" disabled={busy||!moreBatches} onClick={()=>setBatchPage(value=>value+1)}>Đợt trang tiếp →</button><button className="secondary" disabled={busy} onClick={()=>{setEdit(null);setDetail(null);setRefresh(value=>value+1);}}>Tải lại báo cáo</button></div>
    {error&&<p className="error" role="alert">{error}</p>}{message&&<p className="success" role="status">{message}</p>}
    {result&&<>
      <h3>{result.partner.name} · {result.batch.name} · {result.batch.work_date}</h3><p>{result.batch.site} · {labels[result.batch.state]} · Giờ theo {result.batch.timezone} · Tính lúc {time(result.as_of)}</p>
      <dl className="partner-report-stats"><div><dt>Yêu cầu / hạn mức</dt><dd>{result.summary.requested} / {result.summary.capacity}</dd></div><div><dt>Đã Vào</dt><dd>{result.summary.admitted}</dd></div><div><dt>Đủ Vào/Ra</dt><dd>{result.summary.complete}</dd></div><div><dt>Thiếu cặp</dt><dd>{result.summary.incomplete}</dd></div><div><dt>Đang tiếp nhận</dt><dd>{result.summary.pending}</dd></div><div><dt>Giờ đủ điều kiện</dt><dd>{hours(result.summary.total_worked_seconds)}</dd></div></dl>
      <p>{result.note}</p><div className="partner-options"><label>Trạng thái dòng<select value={filter} onChange={event=>{setFilter(event.target.value);setPage(0);}}><option value="all">Tất cả</option><option value="complete">Đủ Vào/Ra</option><option value="incomplete">Đã Vào nhưng thiếu cặp</option><option value="pending">Chờ / hủy / hết phiên tiếp nhận</option></select></label><a className="secondary" href={`/api/admin/partners/batches/${batch}/export.csv?expected_source=${result.source_hash}&status=${filter}`} download>Xuất CSV bản đang xem</a></div>
      <div className="admin-table-wrap"><table><thead><tr><th>Mã tạm / họ tên</th><th>Trạng thái</th><th>Vào đối soát</th><th>Ra đối soát</th><th>Giờ công</th><th>Chi tiết</th></tr></thead><tbody>{rows.slice(page*50,(page+1)*50).map(row=><tr key={row.worker_id}><td><strong>{row.code}</strong><br/>{row.name||'Chưa xác nhận tên'}</td><td>{row.status_label}{row.adjustment_revision>0&&<small> · Đã điều chỉnh {row.adjustment_revision} lần</small>}</td><td>{time(row.in_at)}</td><td>{time(row.out_at)}</td><td>{hours(row.worked_seconds)}</td><td><button className="text-button" onClick={()=>setDetail(row)}>Gốc & lịch sử</button>{!result.closed&&result.batch.state==='review'&&row.admitted&&<button className="text-button" disabled={busy} onClick={()=>{setEdit({row,source:result.source_hash,requestId:crypto.randomUUID(),name:row.name||'',in_local:localDateTimeInput(row.in_at,result.batch.timezone),out_local:localDateTimeInput(row.out_at,result.batch.timezone),reason:''});setError('');}}>Điều chỉnh</button>}</td></tr>)}{!rows.length&&<tr><td colSpan={6}>Không có lao động thuộc bộ lọc này.</td></tr>}</tbody></table></div>
      <div className="form-actions"><button className="text-button" disabled={page===0} onClick={()=>setPage(value=>value-1)}>← Dòng trang trước</button><span>{rows.length} dòng · Trang {page+1}</span><button className="text-button" disabled={(page+1)*50>=rows.length} onClick={()=>setPage(value=>value+1)}>Dòng trang tiếp →</button></div>
      {detail&&<div className="partner-report-detail"><h3>{detail.code} — Lượt gốc và lịch sử</h3><p>Vào camera: {time(detail.raw_in_at)} · Ra camera: {time(detail.raw_out_at)}</p><ul>{detail.original_events.map(event=><li key={event.id}>{event.direction==='in'?'Vào':'Ra'} · {time(event.server_time)} · {event.id}</li>)}</ul><ol>{detail.adjustments.map(item=><li key={item.revision}>Lần {item.revision} · {time(item.at)} · Quản trị #{item.admin_id}: {item.reason}<pre>{JSON.stringify(item.overrides,null,2)}</pre></li>)}</ol>{!detail.adjustments.length&&<p>Chưa có điều chỉnh.</p>}<button className="text-button" onClick={()=>setDetail(null)}>Đóng chi tiết</button></div>}
      {edit&&<form onSubmit={save} className="partner-edit-report"><h3>Điều chỉnh {edit.row.code}</h3><p>Giờ nhập theo {result.batch.timezone}. Bỏ trống thời gian để loại giờ đó khỏi bảng đối soát; lượt gốc và lịch sử vẫn được giữ.</p><label>Họ tên đối soát<input required maxLength={160} value={edit.name} disabled={busy} onChange={event=>setEdit({...edit,name:event.target.value})}/></label><div className="partner-input-row"><label>Giờ Vào đối soát<input type="datetime-local" step="1" value={edit.in_local} disabled={busy} onChange={event=>setEdit({...edit,in_local:event.target.value})}/></label><label>Giờ Ra đối soát<input type="datetime-local" step="1" value={edit.out_local} disabled={busy} onChange={event=>setEdit({...edit,out_local:event.target.value})}/></label></div><label>Lý do điều chỉnh<textarea required minLength={5} maxLength={500} value={edit.reason} disabled={busy} onChange={event=>setEdit({...edit,reason:event.target.value})}/></label><div className="form-actions"><button className="primary" disabled={busy||edit.reason.trim().length<5||!Object.keys(changes).length}>{busy?'Đang lưu…':'Lưu điều chỉnh'}</button><button type="button" className="secondary" disabled={busy} onClick={()=>setEdit(null)}>Đóng biểu mẫu</button></div></form>}
      {result.closed?<div className="partner-close-note"><strong>Đã chốt lúc {time(result.closed_at||null)} · Quản trị #{result.closed_by}</strong><p>{result.close_reason}</p></div>:result.batch.state==='review'&&<div className="partner-close-note"><h3>Chốt đợt</h3><p>Bản chốt lưu riêng cả dữ liệu gốc và điều chỉnh; sau khi chốt không sửa trực tiếp hoặc mở lại đợt này.</p><label>Lý do / ghi chú chốt<textarea minLength={5} maxLength={500} value={closeReason} disabled={busy} onChange={event=>setCloseReason(event.target.value)}/></label>{result.summary.incomplete>0&&<label className="partner-check"><input type="checkbox" checked={ack} disabled={busy} onChange={event=>setAck(event.target.checked)}/>Tôi đã kiểm tra và xác nhận chốt {result.summary.incomplete} dòng còn thiếu Vào/Ra; các dòng này không được tự tính đủ công.</label>}<button className="primary" disabled={busy||closeReason.trim().length<5||(result.summary.incomplete>0&&!ack)} onClick={()=>void close()}>{busy?'Đang chốt…':'Chốt bản đối soát này'}</button></div>}
    </>}
    {!batch&&<p>Chưa có đợt phù hợp bộ lọc. Tạo và cấu hình đợt trước khi tiếp nhận lao động.</p>}
  </div>;
}
