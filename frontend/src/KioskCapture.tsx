import { useEffect, useRef, useState } from 'react';
import { startLocalFaceTracker } from './localFaceTracker';
import { fullFramePhoto } from './cameraCapture';
import { KioskAnnouncement } from './kioskAnnouncement';
import { mirrorFaceBox } from './faceTracking';
import { KioskError, KioskFlow, type FlowState, type Receipt } from './kioskFlow';
import type { KioskDevice } from './PairingPanel';
import './kiosk.css';
import './terminal.css';

export type KioskStatus = {server_time:string; timezone:string; recognition_ready:boolean; attendance_enabled:boolean; attendance_mode?:string|null; pilot_people?:number; pilot_scope?:string; capture_max_edge?:number; message:string; version:string};
const titles: Record<FlowState['phase'],string> = {aligning:'Đang tìm khuôn mặt',processing:'Đang xử lý',waiting:'Chờ đối chiếu',committing:'Đang ghi công',recovering:'Đang kiểm tra kết quả',success:'Đã hoàn tất',retry:'Vui lòng thử lại',offline:'Chưa kết nối máy chủ',disabled:'Dò mặt tự động · chưa ghi công',unauthorized:'Cần ghép lại thiết bị'};

export function KioskCapture({status,device}:{status:KioskStatus|null;device:KioskDevice|null}) {
  const video=useRef<HTMLVideoElement>(null), stream=useRef<MediaStream|null>(null);
  const generation=useRef(0), activeRequest=useRef<AbortController|null>(null), flow=useRef<KioskFlow|null>(null);
  const runtime=useRef({status,device}); runtime.current={status,device};
  const [camera,setCamera]=useState(false),[starting,setStarting]=useState(false);
  const [error,setError]=useState('');
  const [tracking,setTracking]=useState<ReturnType<typeof mirrorFaceBox>>(null);
  const [localBoxes,setLocalBoxes]=useState<number[][] | null>(null);
  useEffect(()=>{
    if(!camera||!video.current){setLocalBoxes(null);return;}
    return startLocalFaceTracker(video.current,setLocalBoxes);
  },[camera]);
  const shownBoxes=localBoxes===null?(tracking?[tracking]:[]):localBoxes.map(mirrorFaceBox).filter(box=>box!==null);
  const autoAttempt=useRef('');
  const [aspect,setAspect]=useState(16/9),[audioMessage,setAudioMessage]=useState('');
  const audio=useRef<HTMLAudioElement>(null),announcement=useRef<KioskAnnouncement|null>(null);
  const [state,setState]=useState<FlowState>({phase:'disabled',feedback:'Bật camera để kiểm tra thiết bị.'});
  const [recent,setRecent]=useState<Receipt[]>([]);
  const [controls,setControls]=useState(false);
  const enabled=!!(status?.attendance_enabled&&device?.active&&device.paired);
  useEffect(()=>{
    setTracking(mirrorFaceBox(state.faceBox));
    const timer=setTimeout(()=>setTracking(null),1800);
    return()=>clearTimeout(timer);
  },[state.faceBox]);

  function stop() {
    generation.current++; flow.current?.stop(); flow.current=null; activeRequest.current?.abort();
    stream.current?.getTracks().forEach(track=>track.stop()); stream.current=null;
    if(video.current)video.current.srcObject=null;
    if(audio.current){audio.current.pause();audio.current.currentTime=0;}
    setCamera(false);setStarting(false);setTracking(null);
    setState({phase:'disabled',feedback:'Camera đã tắt. Bật lại để tiếp tục.'});
  }
  useEffect(()=>{stop();},[device?.id,device?.direction]);
  useEffect(()=>{setRecent([]);},[device?.id,device?.direction]);
  useEffect(()=>{
    if(state.phase==='success'&&state.receipt){
      const saved=state.receipt;
      setRecent(previous=>previous.some(item=>item.event_id===saved.event_id)?previous:[saved,...previous].slice(0,4));
    }
  },[state.phase,state.receipt]);
  useEffect(()=>{
    const key=`kiosk-announced:${device?.id||'unpaired'}`;
    let ids:string[]=[];
    try{const saved=JSON.parse(sessionStorage.getItem(key)||'[]');if(Array.isArray(saved))ids=saved.filter((id:unknown)=>typeof id==='string');}catch{/* Audio history must not prevent recording. */}
    announcement.current=new KioskAnnouncement(ids,values=>{try{sessionStorage.setItem(key,JSON.stringify(values));}catch{/* In-memory deduplication remains active. */}});
  },[device?.id]);
  useEffect(()=>{
    if(state.phase!=='success'||!state.receipt||!audio.current)return;
    const current=generation.current;
    void announcement.current?.announce(state.receipt,async()=>{
      const player=audio.current;if(!player)return;
      player.muted=false;player.volume=1;player.currentTime=0;
      try{await player.play();if(current===generation.current)setAudioMessage('');}
      catch{if(current===generation.current)setAudioMessage('Chưa phát được giọng đọc. Mở “Tùy chọn thiết bị” → “Thử giọng đọc” và kiểm tra âm lượng thiết bị.');}
    });
  },[state.phase,state.receipt]);
  useEffect(()=>{
    const visibility=()=>{if(document.hidden)stop();};document.addEventListener('visibilitychange',visibility);
    return()=>{document.removeEventListener('visibilitychange',visibility);generation.current++;flow.current?.stop();activeRequest.current?.abort();stream.current?.getTracks().forEach(track=>track.stop());};
  },[]);
  useEffect(()=>{
    if(!camera||!device?.paired||!device.active)return;
    const key=`kiosk-pending:${device.id}`;
    let controller:KioskFlow;
    try {
      controller=new KioskFlow({
        enabled:()=>!!(runtime.current.status?.attendance_enabled&&runtime.current.device?.active&&runtime.current.device?.paired),
        load:()=>sessionStorage.getItem(key),save:id=>{if(id)sessionStorage.setItem(key,id);else sessionStorage.removeItem(key);},
        uuid:()=>crypto.randomUUID(),now:()=>performance.now(),update:setState,
        photo:async()=>{if(!video.current)throw new Error('Camera chưa sẵn sàng.');return fullFramePhoto(video.current,runtime.current.status?.capture_max_edge ?? 1280);},
        request:async(path,options={})=>{
          const abort=new AbortController();activeRequest.current=abort;
          const timer=setTimeout(()=>abort.abort(),12000);
          try {
            const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers},signal:abort.signal});
            let body;try{body=await response.json();}catch{throw new KioskError(503,'Chưa nhận được kết quả hợp lệ. Đang kiểm tra lại yêu cầu.');}
            if(!response.ok)throw new KioskError(response.status,typeof body.detail==='string'?body.detail:'Yêu cầu chưa hợp lệ. Đang kiểm tra lại.');
            return body;
          } finally {clearTimeout(timer);if(activeRequest.current===abort)activeRequest.current=null;}
        },
      });
      flow.current=controller;void controller.step();
    } catch {setError('Trình duyệt chưa lưu được mã yêu cầu. Cho phép lưu dữ liệu của trang để dùng chấm công.');return;}
    const timer=setInterval(()=>void controller.step(),500);
    return()=>{clearInterval(timer);controller.stop();if(flow.current===controller)flow.current=null;activeRequest.current?.abort();};
  },[camera,device?.id,device?.direction,device?.paired,device?.active]);

  async function start() {
    const current=++generation.current;setStarting(true);setError('');
    // Unlock this media element within the user's click on iPad/Android.
    if(audio.current){const player=audio.current;player.muted=true;void player.play().then(()=>{if(player.muted){player.pause();player.currentTime=0;player.muted=false;}}).catch(()=>{player.muted=false;});}
    try {
      if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera cần localhost hoặc HTTPS tin cậy.');
      const media=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:1280},height:{ideal:720}},audio:false});
      if(current!==generation.current||!video.current){media.getTracks().forEach(track=>track.stop());return;}
      stream.current=media;video.current.srcObject=media;await video.current.play();
      if(current!==generation.current){media.getTracks().forEach(track=>track.stop());return;}
      setCamera(true);setState({phase:enabled?'aligning':'disabled',feedback:enabled?'Nhìn thẳng và giữ yên. Camera sẽ chụp tự động.':'Camera tự tìm khuôn mặt và kiểm tra chất lượng; chưa ghi công.'});
    } catch(error) {
      if(current!==generation.current)return;
      stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;setCamera(false);
      if(video.current)video.current.srcObject=null;
      setError(error instanceof DOMException&&error.name==='NotAllowedError'?'Chưa được cấp quyền camera. Cho phép camera trong cài đặt trang rồi thử lại.':error instanceof DOMException&&error.name==='NotFoundError'?'Không tìm thấy camera trên thiết bị.':error instanceof Error?error.message:'Chưa mở được camera.');
    } finally {if(current===generation.current)setStarting(false);}
  }
  useEffect(()=>{
    if(!status?.recognition_ready||!device?.paired||!device.active)return;
    const key=`${device.id}:${device.direction}`;
    if(autoAttempt.current===key)return;
    autoAttempt.current=key;void start();
    return()=>{autoAttempt.current='';};
  },[status?.recognition_ready,device?.id,device?.direction,device?.paired,device?.active]);
  const receipt=state.receipt;
  const feedback=!camera?'Cho phép camera khi trình duyệt yêu cầu. Nếu camera chưa mở, bấm Bật camera một lần.':!device?.paired||!device.active?'Ghép quyền thiết bị để camera tự dò mặt.':state.feedback;
  return <section className={`capture kiosk-capture terminal-capture phase-${state.phase}`} aria-label="Camera chấm công">
    <div className="capture-top"><span><i className={camera?'online':''}/>{camera?'Camera đang hoạt động':'Camera trước'}</span><span className="direction">{enabled?(device?.direction==='in'?'VÀO CA':'RA CA'):'DÒ MẶT TỰ ĐỘNG'}</span></div>
    <audio ref={audio} src="/audio/hop-le-dut-khoat.wav" preload="auto"/>
    <div className={`camera-view ${camera?'active':''}`} style={{aspectRatio:aspect}}><video ref={video} muted playsInline autoPlay onLoadedMetadata={()=>{if(video.current?.videoWidth&&video.current.videoHeight)setAspect(video.current.videoWidth/video.current.videoHeight);}} onResize={()=>{if(video.current?.videoWidth&&video.current.videoHeight)setAspect(video.current.videoWidth/video.current.videoHeight);}} aria-label="Toàn cảnh camera chấm công"/>
      {!camera&&<div className="kiosk-camera-placeholder">Toàn cảnh camera<br/><small>Tự tìm khuôn mặt trong hình</small></div>}
      {camera&&shownBoxes.map((box,index)=><div key={index} className="kiosk-tracking-box" style={box} aria-label="Vị trí khuôn mặt đang phát hiện"><span>Đã thấy khuôn mặt</span></div>)}
      {camera&&<div className="terminal-camera-label">{device?.name||'Camera chấm công'}<span>Toàn cảnh · Tự nhận diện</span></div>}
    </div>
    <aside className="terminal-recent" aria-label="Lượt chấm công vừa ghi nhận"><div className="terminal-recent-heading"><span>VỪA GHI NHẬN</span><small>Trên thiết bị này</small></div>
      {recent.length===0?<div className="terminal-empty"><span aria-hidden="true">✓</span><strong>Sẵn sàng đón bạn</strong><p>Các lượt đã được máy chủ xác nhận sẽ xuất hiện tại đây.</p></div>:<ol>{recent.map(item=><li key={item.event_id}><div className="terminal-avatar" aria-hidden="true">{item.employee_name.trim().split(/\s+/).slice(-2).map(part=>part[0]).join('')}</div><div className="terminal-person"><strong>{item.employee_name}</strong><small>{item.employee_code}</small><div><span className={`terminal-event ${item.direction}`}>{item.direction==='in'?'Vào':'Ra'}</span><time dateTime={item.server_time}>{new Date(item.server_time).toLocaleTimeString('vi-VN',{timeZone:status?.timezone||'Asia/Ho_Chi_Minh',hour12:false})}</time></div></div></li>)}</ol>}
      <p className="terminal-session-note">Hiển thị tối đa 4 lượt trong phiên mở trang.</p>
    </aside>
    <div className="capture-bottom"><div className="terminal-result" role="status" aria-live="polite"><span className={`terminal-result-icon ${state.phase==='success'?'valid':''}`} aria-hidden="true">{state.phase==='success'?'✓':'◎'}</span><div className="kiosk-progress"><strong>{receipt&&state.phase==='success'?(receipt.status==='duplicate'?'Đã ghi nhận trước đó':'Hợp lệ'):camera?titles[state.phase]:'Sẵn sàng chấm công'}</strong>{receipt&&state.phase==='success'?<p className="terminal-confirmed-name">{receipt.employee_name}<span>{receipt.employee_code} · {receipt.direction==='in'?'Vào ca':'Ra ca'} · {new Date(receipt.server_time).toLocaleTimeString('vi-VN',{timeZone:status?.timezone||'Asia/Ho_Chi_Minh',hour12:false})}</span></p>:<p>{feedback}</p>}</div></div>
      <div className="terminal-actions">{!camera&&<button onClick={()=>void start()} disabled={starting}>{starting?'Đang mở camera…':'Bật camera'}</button>}<button className="secondary terminal-settings-button" onClick={()=>setControls(!controls)} aria-expanded={controls}>{controls?'Đóng tùy chọn':'Tùy chọn thiết bị'}</button></div>
      {controls&&<div className="terminal-controls">{camera&&<button className="secondary" onClick={stop}>Tắt camera</button>}
      <button className="secondary kiosk-audio-test" onClick={()=>{const player=audio.current;if(player){player.muted=false;player.volume=1;player.currentTime=0;void player.play().then(()=>setAudioMessage('Đây là thử giọng đọc, không ghi chấm công.')).catch(()=>setAudioMessage('Chưa phát được âm thanh. Kiểm tra âm lượng và quyền phát âm thanh của trình duyệt.'));}}}>Thử giọng đọc</button></div>}
      {error&&<p className="error" role="alert">{error}</p>}
      {audioMessage&&<p role="status">{audioMessage}</p>}
      {status?.attendance_mode==='functional_trial'&&<p className="kiosk-auto-note terminal-trial-note">Chấm công thử {status.pilot_people ?? 1} hồ sơ · Chưa nghiệm thu độ chính xác theo nhóm và chống ảnh giả.</p>}
    </div>
  </section>;
}
