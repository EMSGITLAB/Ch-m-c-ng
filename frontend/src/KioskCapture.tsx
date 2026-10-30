import { useEffect, useRef, useState } from 'react';
import { startLocalFaceTracker } from './localFaceTracker';
import { fullFramePhoto } from './cameraCapture';
import { KioskAnnouncement } from './kioskAnnouncement';
import { mirrorFaceBox, sceneLayout } from './faceTracking';
import { KioskError, KioskFlow, type FlowState, type Receipt } from './kioskFlow';
import { PairingPanel, type KioskDevice } from './PairingPanel';
import { kioskReadiness } from './kioskReadiness';
import { connectCameraOwner } from './cameraLease';
import './kiosk.css';
import './terminal.css';

export type KioskStatus = {server_time:string; timezone:string; recognition_ready:boolean; attendance_enabled:boolean; attendance_mode?:string|null; pilot_people?:number; pilot_scope?:string; capture_max_edge?:number; message:string; version:string};
const titles: Record<FlowState['phase'],string> = {aligning:'Đang tìm khuôn mặt',processing:'Đang xử lý',waiting:'Chờ đối chiếu',committing:'Đang ghi công',recovering:'Đang kiểm tra kết quả',success:'Đã hoàn tất',retry:'Vui lòng thử lại',offline:'Chưa kết nối máy chủ',disabled:'Dò mặt tự động · chưa ghi công',unauthorized:'Cần ghép lại thiết bị'};

export function KioskCapture({status,device,onDirectionChange,onDeviceChange,directionBusy=false}:{status:KioskStatus|null;device:KioskDevice|null;onDeviceChange?:(device:KioskDevice|null)=>void;onDirectionChange?:(direction:'in'|'out')=>void;directionBusy?:boolean}) {
  const cameraView=useRef<HTMLDivElement>(null);
  const video=useRef<HTMLVideoElement>(null), stream=useRef<MediaStream|null>(null);
  const generation=useRef(0), activeRequest=useRef<AbortController|null>(null), flow=useRef<KioskFlow|null>(null);
  const cameraOwner=useRef<ReturnType<typeof connectCameraOwner>|null>(null);
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
  const [aspect,setAspect]=useState(4/3),[audioMessage,setAudioMessage]=useState('');
  const [scene,setScene]=useState<ReturnType<typeof sceneLayout>>({});
  useEffect(()=>{
    const element=cameraView.current;if(!element)return;
    const resize=()=>{const r=element.getBoundingClientRect();setScene(sceneLayout(r.width,r.height,aspect));};
    resize();const observer=new ResizeObserver(resize);observer.observe(element);
    return()=>observer.disconnect();
  },[aspect]);
  const audio=useRef<HTMLAudioElement>(null),announcement=useRef<KioskAnnouncement|null>(null);
  const [state,setState]=useState<FlowState>({phase:'disabled',feedback:'Bật camera để kiểm tra thiết bị.'});
  const [recent,setRecent]=useState<Receipt[]>([]);
  const [controlsOpen,setControlsOpen]=useState(false);
  const [pairingOpen,setPairingOpen]=useState(false);
  const [facingMode,setFacingMode]=useState<'user'|'environment'>('user');
  const readiness=kioskReadiness(status,device);
  const enabled=readiness.canRecord;
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
  useEffect(()=>{const owner=connectCameraOwner(stop);cameraOwner.current=owner;return()=>{owner.close();cameraOwner.current=null;};},[]);
  useEffect(()=>{setRecent([]);},[device?.id,device?.direction]);
  useEffect(()=>{
    if(state.phase==='success'&&state.receipt?.status==='recorded'){
      const saved=state.receipt;
      setRecent(previous=>previous.some(item=>item.event_id===saved.event_id)?previous:[saved,...previous].slice(0,6));
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
      catch{if(current===generation.current)setAudioMessage('Chưa phát được giọng đọc. Mở “Tùy chọn” → “Thử giọng đọc” và kiểm tra âm lượng thiết bị.');}
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
        enabled:()=>kioskReadiness(runtime.current.status,runtime.current.device).canRecord,
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

  async function start(requestedFacing = facingMode) {
    const current=++generation.current;setStarting(true);setError('');
    cameraOwner.current?.claim();
    // Unlock this media element within the user's click on iPad/Android.
    if(audio.current){const player=audio.current;player.muted=true;void player.play().then(()=>{if(player.muted){player.pause();player.currentTime=0;player.muted=false;}}).catch(()=>{player.muted=false;});}
    try {
      if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera cần localhost hoặc HTTPS tin cậy.');
      await new Promise(resolve=>setTimeout(resolve,200));
      if(current!==generation.current)return;
      const media=await navigator.mediaDevices.getUserMedia({video:{facingMode:requestedFacing,width:{ideal:1280},height:{ideal:720}},audio:false});
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
  function toggleCameraFlip() {
    const next = facingMode === 'user' ? 'environment' : 'user';
    setFacingMode(next);
    if(camera) { stop(); void start(next); }
  }
  async function testAudio() {
    const player = audio.current; if(!player)return;
    player.muted=false;player.volume=1;player.currentTime=0;
    try { await player.play();setAudioMessage('Đây là thử giọng đọc, không ghi chấm công.'); }
    catch { setAudioMessage('Chưa phát được âm thanh. Kiểm tra âm lượng và quyền phát âm thanh.'); }
  }
  const receipt = state.receipt;
  const feedback = !readiness.canRecord ? readiness.feedback : !camera
    ? 'Bấm “Bật camera” hoặc mở “Tùy chọn” để tiếp tục nhận diện.'
    : !device?.paired || !device.active
      ? 'Ghép quyền thiết bị để camera tự dò mặt.'
      : state.feedback;

  const currentDir = device?.direction || 'in';

  return (
    <section className={`capture kiosk-capture terminal-capture phase-${state.phase}`} aria-label="Camera chấm công">
      {/* Top HUD Bar */}
      <div className="capture-top">
        <div className="capture-status-badge">
          <i className={camera ? 'online pulse' : ''} />
          <span>{!readiness.canRecord ? readiness.title : camera ? (facingMode === 'user' ? 'Camera trước · Đang quét' : 'Camera sau · Đang quét') : 'Camera chưa bật'}</span>
        </div>

        <div className="capture-direction-switch">
          <button
            type="button"
            className={`direction-toggle-btn ${currentDir === 'in' ? 'active-in' : ''}`}
            disabled={!device?.paired || directionBusy}
            onClick={() => onDirectionChange?.('in')}
            title="Chuyển sang chế độ Vào Ca"
          >
            <span>↓</span> Vào ca
          </button>
          <button
            type="button"
            className={`direction-toggle-btn ${currentDir === 'out' ? 'active-out' : ''}`}
            disabled={!device?.paired || directionBusy}
            onClick={() => onDirectionChange?.('out')}
            title="Chuyển sang chế độ Ra Ca"
          >
            <span>↑</span> Ra ca
          </button>
        </div>
        <button className="kiosk-options-button" aria-expanded={controlsOpen} aria-controls="kiosk-option-controls" onClick={()=>setControlsOpen(value=>!value)}>⚙ {controlsOpen?'Đóng tùy chọn':'Tùy chọn'}</button>
        {controlsOpen && <div className="kiosk-option-controls" id="kiosk-option-controls" aria-label="Tùy chọn camera và thiết bị">
          <button className="secondary-pill-btn" onClick={()=>camera||starting?stop():void start()}>{starting?'Hủy mở camera':camera?'Tắt camera':'Bật camera'}</button>
          <button className="secondary-pill-btn" disabled={!camera} onClick={toggleCameraFlip}>Đổi camera trước/sau</button>
          <button className="secondary-pill-btn" onClick={()=>setPairingOpen(true)}>Ghép thiết bị</button>
          <button className="secondary-pill-btn" onClick={()=>void testAudio()}>Thử giọng đọc</button>
        </div>}
      </div>

      <audio ref={audio} src="/audio/hop-le-user-fast-135.wav" preload="auto" />

      {/* Main Viewfinder Frame */}
      <div ref={cameraView} className={`camera-view ${camera ? 'active' : ''}`} style={{ aspectRatio: aspect }}>

        <div className="camera-scene" style={scene}>
        <video
          ref={video}
          muted
          playsInline
          autoPlay
          onLoadedMetadata={() => {
            if (video.current?.videoWidth && video.current.videoHeight) {
              setAspect(video.current.videoWidth / video.current.videoHeight);
            }
          }}
          aria-label="Toàn cảnh camera chấm công"
        />
        {/* Real-time Bounding Box Overlays */}
        {camera &&
          shownBoxes.map((box, index) => (
            <div key={index} className="kiosk-tracking-box" style={box} aria-label="Vị trí khuôn mặt phát hiện">
              <span className="box-indicator">Đã định vị khuôn mặt</span>
            </div>
          ))}

        </div>

        {/* Biometric Scanning Corners HUD */}
        <div className="scanner-hud-overlay" aria-hidden="true">
          <div className="scanner-reticle-corner corner-top-left" />
          <div className="scanner-reticle-corner corner-top-right" />
          <div className="scanner-reticle-corner corner-bottom-left" />
          <div className="scanner-reticle-corner corner-bottom-right" />
          {camera && state.phase !== 'success' && <div className="scanner-laser-line" />}
        </div>

        {!camera && (
          <div className="kiosk-camera-placeholder">
            <div className="placeholder-icon">📷</div>
            <strong>{readiness.canRecord ? 'Camera Sẵn Sàng' : readiness.title}</strong>
            <p>{readiness.canRecord ? 'Bật camera để tự động nhận diện và chấm công' : readiness.feedback}</p>
            <div className="placeholder-actions">
              <button className="primary-pill-btn" onClick={() => readiness.code==='unpaired' ? setPairingOpen(true) : void start()} disabled={starting}>
                {readiness.code==='unpaired' ? 'Ghép điểm chấm công' : starting ? 'Đang khởi động camera…' : 'Bật camera'}
              </button>
            </div>
          </div>
        )}


        {camera && (
          <div className="terminal-camera-label">
            <div className="camera-label-tag">
              <span className="live-dot" />
              <span>{device?.name || 'Điểm Chấm Công Tablet'}</span>
            </div>

          </div>
        )}

        {/* Success Modal Overlay */}
        {state.phase === 'success' && receipt && (
          <div className="success-celebration-overlay" role="alert" aria-live="assertive">
            <div className="celebration-card">
              <div className="celebration-badge-ring">
                <span className="celebration-icon">✓</span>
              </div>
              <span className="celebration-kicker">{receipt.status === 'duplicate' ? receipt.direction === 'in' ? 'ĐÃ QUÉT VÀO CA' : 'ĐÃ QUÉT RA CA' : 'ĐIỂM DANH HỢP LỆ'}</span>
              <h2 className="celebration-name">{receipt.employee_name}</h2>
              <div className="celebration-details">
                <span className="celebration-code">{receipt.employee_code}</span>
                <span className="celebration-sep">·</span>
                <span className={`celebration-dir ${receipt.direction}`}>{receipt.direction === 'in' ? 'Vào ca' : 'Ra ca'}</span>
                <span className="celebration-sep">·</span>
                <time className="celebration-time">
                  {new Date(receipt.server_time).toLocaleTimeString('vi-VN', {
                    timeZone: status?.timezone || 'Asia/Ho_Chi_Minh',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </time>
              </div>
              <p className="celebration-wish">{receipt.status === 'duplicate' ? 'Giữ nguyên giờ đã ghi nhận. Không ghi thêm lượt.' : 'Chúc bạn một ngày làm việc hiệu quả và nhiều niềm vui!'}</p>
            </div>
          </div>
        )}
      </div>

      {/* Recent Punches Feed on iPad / Tablet */}
      <aside className="terminal-recent" aria-label="Lượt chấm công vừa ghi nhận">
        <div className="terminal-recent-heading">
          <div className="recent-heading-text">
            <span>VỪA GHI NHẬN</span>
            <small>Điểm danh gần nhất</small>
          </div>
          <span className="recent-counter-badge">{recent.length}</span>
        </div>

        {recent.length === 0 ? (
          <div className="terminal-empty">
            <span className="empty-icon" aria-hidden="true">
              ⏳
            </span>
            <strong>Sẵn sàng đón bạn</strong>
            <p>Đứng trước camera và giữ yên trong giây lát để tự động chấm công.</p>
          </div>
        ) : (
          <ol className="recent-punches-list">
            {recent.map(item => (
              <li key={item.event_id} className="recent-item">
                <div className="terminal-avatar" aria-hidden="true">
                  {item.employee_name
                    .trim()
                    .split(/\s+/)
                    .slice(-2)
                    .map(part => part[0])
                    .join('')}
                </div>
                <div className="terminal-person">
                  <strong>{item.employee_name}</strong>
                  <div className="person-sub">
                    <span className="emp-code">{item.employee_code}</span>
                    <span className={`terminal-event ${item.direction}`}>{item.direction === 'in' ? 'Vào ca' : 'Ra ca'}</span>
                    <time dateTime={item.server_time}>
                      {new Date(item.server_time).toLocaleTimeString('vi-VN', {
                        timeZone: status?.timezone || 'Asia/Ho_Chi_Minh',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </time>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
        <p className="terminal-session-note">Kết quả được xác nhận và lưu tại máy chủ nội bộ.</p>
      </aside>

      {/* Bottom Bar Controls & Progress */}
      <div className="capture-bottom">
        <div className="terminal-result" role="status" aria-live="polite">
          <div className={`terminal-result-icon ${state.phase === 'success' ? 'valid' : ''}`}>
            {state.phase === 'success' ? '✓' : camera ? '◎' : '⚡'}
          </div>

          <div className="kiosk-progress">
            <div className="progress-title-row">
              <strong>{receipt && state.phase === 'success' ? receipt.status === 'duplicate' ? receipt.direction === 'in' ? 'Đã quét vào ca' : 'Đã quét ra ca' : 'Đã xác thực hợp lệ' : !readiness.canRecord ? readiness.title : camera ? titles[state.phase] : 'Chấm công sẵn sàng'}</strong>

              {/* 3 Steps indicator */}
              {camera && state.phase !== 'success' && (
                <div className="step-pips" aria-label="Độ ổn định khuôn mặt">
                  <span className={`step-pip ${state.stableFrames && state.stableFrames >= 1 ? 'active' : ''}`} />
                  <span className={`step-pip ${state.stableFrames && state.stableFrames >= 2 ? 'active' : ''}`} />
                  <span className={`step-pip ${state.stableFrames && state.stableFrames >= 3 ? 'active' : ''}`} />
                </div>
              )}
            </div>

            <p className="feedback-message">{feedback}</p>
          </div>
        </div>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {audioMessage && <p className="audio-feedback">{audioMessage}</p>}
      </div>

      {pairingOpen && <div className="demo-modal-backdrop" onClick={()=>setPairingOpen(false)}><div className="demo-modal-dialog kiosk-pairing-dialog" role="dialog" aria-modal="true" aria-labelledby="pair-kiosk-title" onClick={e=>e.stopPropagation()}><div className="demo-modal-header"><div><h3 id="pair-kiosk-title">Ghép quyền chấm công cho trình duyệt</h3><p>Lấy mã tại Quản trị → Thiết bị Kiosk.</p></div><button className="modal-close-btn" aria-label="Đóng ghép kiosk" onClick={()=>setPairingOpen(false)}>✕</button></div><div className="demo-modal-body"><PairingPanel initiallyOpen allowRePair onDevice={next=>onDeviceChange?.(next)} onPaired={()=>setPairingOpen(false)}/><a className="primary-pill-btn" href="#admin/devices">Lấy mã ghép 8 số trong Quản trị → Thiết bị Kiosk</a></div></div></div>}
    </section>
  );
}
