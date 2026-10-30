import { useEffect, useState } from 'react';
import { FaceCollectionPanel } from './FaceCollectionPanel';

type Person = {employee_id:string;employee_code:string;employee_name:string;enrollment_samples:number;calibration_samples:number;calibration_collections:number;role:string;missing_calibration_samples:number};
type Coverage = {items:Person[];total:number;offset:number;limit:number;minimum_probe_samples:number;summary:{enrolled_people:number;known_people_missing_probes:number;known_probe_samples_missing:number;outside_probe_people:number;outside_people_missing:number;data_coverage_ready:boolean}};

export function CalibrationCoveragePanel({csrf,onUnauthorized,onChanged}:{csrf:string;onUnauthorized:()=>void;onChanged:()=>void}) {
  const [data,setData]=useState<Coverage|null>(null),[error,setError]=useState(''),[offset,setOffset]=useState(0),[refresh,setRefresh]=useState(0),[collecting,setCollecting]=useState<Person|null>(null);
  useEffect(()=>{
    const controller=new AbortController();setError('');setData(null);
    void fetch(`/api/admin/recognition/calibration/coverage?offset=${offset}&limit=100`,{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(15000)])})
      .then(async response=>{const body=await response.json();if(response.status===401)onUnauthorized();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Chưa đọc được danh sách mẫu.');if(!controller.signal.aborted)setData(body);})
      .catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Chưa đọc được dữ liệu.');});
    return()=>controller.abort();
  },[offset,refresh]);
  if(collecting)return <FaceCollectionPanel key={collecting.employee_id} employee={{id:collecting.employee_id,code:collecting.employee_code,name:collecting.employee_name}} initialPurpose="calibration" csrf={csrf} onUnauthorized={onUnauthorized} onClose={()=>{setCollecting(null);setRefresh(v=>v+1);onChanged();}}/>;
  return <div className="calibration-coverage"><h3>Ảnh đăng ký và ảnh dùng để kiểm tra</h3>
    <p className="section-explanation">Ảnh nhân sự đã nhập là ảnh tham chiếu. Ảnh hiệu chỉnh là ảnh mới của cùng người ở phiên chụp khác, dùng để thử xem camera có nhận ra họ hay không. Một ảnh tham chiếu vẫn được hỗ trợ; không cần nhân bản ảnh đã nhập.</p>
    {error&&<p className="error" role="alert">{error}</p>}
    {!data&&!error&&<p>Đang đọc số lượng mẫu…</p>}
    {data && data.summary && <><p className="section-explanation">Có {data.summary.enrolled_people} người có ảnh đăng ký; {data.summary.known_people_missing_probes} người còn thiếu ảnh hiệu chỉnh, tổng {data.summary.known_probe_samples_missing} khung theo cấu hình thử hiện tại. Còn thiếu {data.summary.outside_people_missing} người ngoài có đủ mẫu. Mỗi phiên thu hiệu chỉnh hiện lấy tối thiểu {data.minimum_probe_samples || 3} khung đạt; camera hỗ trợ tự chụp.</p>
      <div className="employee-table"><table><thead><tr><th>Nhân viên</th><th>Ảnh đăng ký</th><th>Ảnh hiệu chỉnh / phiên</th><th>Tình trạng</th><th>Thao tác</th></tr></thead><tbody>{(data.items || []).map(person=><tr key={person.employee_id}><td>{person.employee_code} · {person.employee_name}</td><td>{person.enrollment_samples}</td><td>{person.calibration_samples} / {person.calibration_collections}</td><td>{person.role==='enrolled'?(person.missing_calibration_samples?`Thiếu ${person.missing_calibration_samples} khung hiệu chỉnh`:'Đã có bộ hiệu chỉnh'):person.role==='outside_probe'?'Mẫu người ngoài bộ đăng ký':'Chưa có bộ mẫu hoàn tất'}</td><td><button className="text-button" onClick={()=>setCollecting(person)}>Thu ảnh hiệu chỉnh mới</button></td></tr>)}</tbody></table></div>
      <p className="section-explanation">Người ngoài bộ đăng ký là hồ sơ thử có ảnh hiệu chỉnh nhưng chưa có ảnh đăng ký trong gallery. Không xóa ảnh nhân viên đang dùng chỉ để tạo đủ nhóm người ngoài. Tập kiểm tra cuối được giữ riêng.</p>
      <div className="pagination"><span>{data.total?data.offset+1:0}–{Math.min(data.offset+(data.items?.length || 0),data.total || 0)} / {data.total || 0}</span><button className="text-button" onClick={()=>setOffset(v=>Math.max(0,v-100))} disabled={offset===0}>Trang trước</button><button className="text-button" onClick={()=>setOffset(v=>v+100)} disabled={offset+(data.items?.length || 0)>=(data.total || 0)}>Trang sau</button></div>
    </>}
  </div>;
}
