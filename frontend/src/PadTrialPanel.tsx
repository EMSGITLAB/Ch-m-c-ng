import { useEffect, useRef, useState } from 'react';
import { fullFramePhoto } from './cameraCapture';
import { runPadTrial, type PadObservation } from './padTrial';
import './pad.css';

const scenarios:Record<string,string>={unlabelled:'Chưa gán nhãn — thử đường xử lý',live:'Người thật trực tiếp',print:'Ảnh in trên giấy',screen:'Ảnh tĩnh trên màn hình',replay:'Video phát lại trên màn hình'};
type Trial = Awaited<ReturnType<typeof runPadTrial>> & {scenario:string;scenario_label:string;ground_truth_source:'operator_declared';conditions:string};

export function PadTrialPanel({csrf,onUnauthorized}:{csrf:string;onUnauthorized:()=>void}) {
  const video=useRef<HTMLVideoElement>(null),stream=useRef<MediaStream|null>(null),generation=useRef(0),pending=useRef<AbortController|null>(null);
  const [ready,setReady]=useState<boolean|null>(null),[camera,setCamera]=useState(false),[busy,setBusy]=useState(false),[starting,setStarting]=useState(false),[count,setCount]=useState(0);
  const [scenario,setScenario]=useState('unlabelled'),[conditions,setConditions]=useState(''),[error,setError]=useState(''),[trial,setTrial]=useState<Trial|null>(null),[aspect,setAspect]=useState(16/9);
  function stop(){generation.current++;pending.current?.abort();stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;if(video.current)video.current.srcObject=null;setCamera(false);setBusy(false);setStarting(false);}
  useEffect(()=>{
    const controller=new AbortController();
    void fetch('/api/admin/pad/status',{signal:controller.signal}).then(async response=>{if(response.status===401)onUnauthorized();if(!response.ok)throw new Error('Chưa đọc được trạng thái PAD.');const body=await response.json();if(!controller.signal.aborted)setReady(body.ready===true);}).catch(()=>{if(!controller.signal.aborted)setReady(false);});
    const visibility=()=>{if(document.hidden)stop();};document.addEventListener('visibilitychange',visibility);
    return()=>{controller.abort();document.removeEventListener('visibilitychange',visibility);generation.current++;pending.current?.abort();stream.current?.getTracks().forEach(track=>track.stop());};
  },[]);
  async function start(){
    const current=++generation.current;setStarting(true);setError('');
    try{
      if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera cần localhost hoặc HTTPS tin cậy.');
      const media=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:1280},height:{ideal:720}},audio:false});
      if(current!==generation.current||!video.current){media.getTracks().forEach(track=>track.stop());return;}
      stream.current=media;video.current.srcObject=media;await video.current.play();
      if(current===generation.current)setCamera(true);else media.getTracks().forEach(track=>track.stop());
    }catch(e){if(current===generation.current){stop();setError(e instanceof Error?e.message:'Chưa mở được camera.');}}
    finally{if(current===generation.current)setStarting(false);}
  }
  async function measure(){
    if(!camera||busy||!video.current)return;
    const current=generation.current,declaredScenario=scenario,declaredConditions=conditions.trim();
    const controller=new AbortController();pending.current=controller;setBusy(true);setCount(0);setError('');setTrial(null);
    try{
      const result=await runPadTrial({current:()=>current===generation.current&&!controller.signal.aborted,photo:()=>fullFramePhoto(video.current!),update:setCount,
        pause:()=>new Promise<void>((resolve,reject)=>{const aborted=()=>{clearTimeout(timer);reject(new DOMException('Đã dừng.','AbortError'));};const timer=setTimeout(()=>{controller.signal.removeEventListener('abort',aborted);resolve();},500);controller.signal.addEventListener('abort',aborted,{once:true});}),
        preview:async photo=>{
          const response=await fetch('/api/admin/pad/preview',{method:'POST',headers:{'Content-Type':'image/jpeg','X-CSRF-Token':csrf,'X-PAD-Intent':'experimental-pad-preview'},body:photo,signal:AbortSignal.any([controller.signal,AbortSignal.timeout(15000)])});
          const body=await response.json();if(response.status===401)onUnauthorized();
          if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Chưa đo được điểm chống giả mạo.');return body as PadObservation;
        }});
      if(current===generation.current)setTrial({...result,scenario:declaredScenario,scenario_label:scenarios[declaredScenario],ground_truth_source:'operator_declared',conditions:declaredConditions});
    }catch(e){if(current===generation.current)setError(e instanceof Error?e.message:'Phép thử chưa hoàn tất.');}
    finally{if(current===generation.current)setBusy(false);if(pending.current===controller)pending.current=null;}
  }
  function download(){if(!trial)return;const url=URL.createObjectURL(new Blob([JSON.stringify(trial,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='pad-trial-local.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
  return <section className="pad-panel" aria-label="Kiểm chứng chống giả mạo">
    <h2>Kiểm chứng chống ảnh giả</h2><p>Thử riêng người thật, ảnh in, ảnh trên màn hình và video phát lại. Model chạy local; điểm đo chưa có ngưỡng đã kiểm chứng và chưa dùng bật ghi công.</p>
    <div className="pad-layout"><div className="pad-camera" style={{aspectRatio:aspect}}><video ref={video} autoPlay muted playsInline aria-label="Camera kiểm chứng chống giả mạo" onLoadedMetadata={()=>{if(video.current?.videoWidth&&video.current.videoHeight)setAspect(video.current.videoWidth/video.current.videoHeight);}}/>{!camera&&<span>Camera kiểm chứng riêng</span>}</div><div>
      <label>Loại tình huống thực tế<select value={scenario} onChange={e=>setScenario(e.target.value)} disabled={busy}>{Object.entries(scenarios).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      <label>Điều kiện thử — không nhập tên người<textarea value={conditions} maxLength={500} onChange={e=>setConditions(e.target.value)} disabled={busy} placeholder="Ví dụ: camera laptop, ánh sáng phòng, ảnh trên điện thoại cách 50 cm"/></label>
      <p>{ready===null?'Đang kiểm tra model…':ready?'Hai model PAD local sẵn sàng để đo thử.':'Model PAD chưa sẵn sàng. Kiểm tra bộ model tại máy chủ.'}</p>
      {camera?<><button onClick={()=>void measure()} disabled={busy||!ready}>{busy?`Đang đo ${count}/5 khung…`:'Đo tự động 5 khung hình'}</button><button className="secondary" onClick={stop}>Dừng camera / phép thử</button></>:<button onClick={()=>void start()} disabled={starting||!ready}>{starting?'Đang mở camera…':'Mở camera kiểm chứng'}</button>}
    </div></div>
    {error&&<p className="error" role="alert">{error}</p>}
    {trial&&<div className="pad-trial-result" role="status"><h3>Kết quả phiên thử — chưa kết luận đạt PAD</h3><p>{trial.scenario_label} · {trial.quality_accepted_frames}/5 ảnh đủ chất lượng · {trial.context_clipped_frames} ảnh có vùng ngữ cảnh bị cắt.</p><p>Điểm lớp người thật: {trial.live_score_mean===null?'Chưa có ảnh đủ chất lượng.':`trung bình ${trial.live_score_mean.toFixed(3)}, thấp nhất ${trial.live_score_min!.toFixed(3)}, cao nhất ${trial.live_score_max!.toFixed(3)}.`}</p><ul>{trial.readings.map((row,index)=><li key={index}>Khung {index+1}: {row.pad?`score ${row.pad.ensemble_live_score.toFixed(3)} · ${row.pad.pad_ms.toFixed(1)} ms`:row.feedback||row.reason||'Chưa đạt chất lượng.'}</li>)}</ul><button className="secondary" onClick={download}>Tải báo cáo JSON của phiên</button><p>5 khung trong cùng phiên có tương quan; không tính là 5 người hoặc 5 phép thử độc lập. Không lưu ảnh/vector vào báo cáo. Nhãn tình huống do người thử tự khai báo; chưa phải kết quả nghiệm thu.</p></div>}
  </section>;
}
