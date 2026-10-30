import { useEffect, useRef, useState } from 'react';
import { fullFramePhoto } from './cameraCapture';
import { mirrorFaceBox } from './faceTracking';
import { KioskAnnouncement } from './kioskAnnouncement';
import { KioskError } from './kioskFlow';
import { LocalNameRecorder } from './LocalNameRecorder';
import { startLocalFaceTracker } from './localFaceTracker';
import { PairingPanel, type KioskDevice } from './PairingPanel';
import { PartnerFlow, type PartnerState } from './partnerFlow';
import { PartnerNameDialog } from './PartnerNameDialog';
import { connectCameraOwner } from './cameraLease';
import { PartnerAudioCue } from './PartnerAudioCue';
import './partner.css';

type Context={partner:{name:string;code:string};batch:{id:string;name:string;site:string;state:string;starts_at:string;ends_at:string;timezone:string;rules:{functional_trial?:boolean}};direction:'in'|'out';recognition_ready:boolean;recording_enabled:boolean;message:string};
export function PartnerKioskCapture({device,onDeviceChange,onDirectionChange,directionBusy=false}:{device:KioskDevice|null;onDeviceChange:(device:KioskDevice|null)=>void;onDirectionChange:(direction:'in'|'out')=>void;directionBusy?:boolean}){
  const [context,setContext]=useState<Context|null>(null),[error,setError]=useState('');
  const [camera,setCamera]=useState(false),[starting,setStarting]=useState(false),[options,setOptions]=useState(false),[pairing,setPairing]=useState(false);
  const [aspect,setAspect]=useState(4/3),[boxes,setBoxes]=useState<number[][]|null>(null);
  const [state,setState]=useState<PartnerState>({phase:'scanning',feedback:'Bật camera để bắt đầu.'});
  const [name,setName]=useState(''),[source,setSource]=useState<'manual'|'voice'|'voice_edited'>('manual');
  const [nameBusy,setNameBusy]=useState(false),[voice,setVoice]=useState<'idle'|'starting'|'recording'|'processing'>('idle');
  const [voiceMessage,setVoiceMessage]=useState(''),[audioMessage,setAudioMessage]=useState('');
  const video=useRef<HTMLVideoElement>(null),stream=useRef<MediaStream|null>(null),audio=useRef<HTMLAudioElement>(null);
  const generation=useRef(0),requests=useRef(new Set<AbortController>()),flow=useRef<PartnerFlow|null>(null);
  const recorder=useRef(new LocalNameRecorder()),voiceGeneration=useRef(0),announcement=useRef<KioskAnnouncement|null>(null);
  const auto=useRef(''),lastWorker=useRef(''),voiceAbort=useRef<AbortController|null>(null);
  const cameraOwner=useRef<ReturnType<typeof connectCameraOwner>|null>(null);
  const audioCue=useRef<PartnerAudioCue|null>(null);
  useEffect(()=>{if(!audio.current)return;const cue=new PartnerAudioCue(audio.current);audioCue.current=cue;return()=>{cue.close();if(audioCue.current===cue)audioCue.current=null;};},[]);
  async function request(path:string,options:RequestInit={}){
    const controller=new AbortController();requests.current.add(controller);
    const timeout=setTimeout(()=>controller.abort(),12000);
    try{
      const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers},signal:controller.signal});
      const body=await response.json();
      if(!response.ok)throw new KioskError(response.status,typeof body.detail==='string'?body.detail:'Yêu cầu chưa hợp lệ.');
      return body;
    }finally{clearTimeout(timeout);requests.current.delete(controller);}
  }
  function cancelVoice(){voiceGeneration.current++;recorder.current.cancel();voiceAbort.current?.abort();voiceAbort.current=null;setVoice('idle');}
  function unlockAudio(){
    audioCue.current?.unlock();
  }
  function stop(){
    generation.current++;flow.current?.stop();flow.current=null;
    requests.current.forEach(controller=>controller.abort());requests.current.clear();
    stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;
    if(video.current)video.current.srcObject=null;
    cancelVoice();setCamera(false);setStarting(false);setBoxes(null);setNameBusy(false);
  }
  useEffect(()=>{const owner=connectCameraOwner(stop);cameraOwner.current=owner;return()=>{owner.close();cameraOwner.current=null;};},[]);
  useEffect(()=>{
    const controller=new AbortController();let alive=true;
    async function refresh(){
      try{
        const response=await fetch('/api/kiosk/partners/context',{signal:controller.signal});const body=await response.json();
        if(!alive)return;
        if(!response.ok){setContext(null);setError(typeof body.detail==='string'?body.detail:'Chưa có cấu hình điểm đối tác.');return;}
        setContext(body);setError(body.recording_enabled?'':body.message);
      }catch{if(alive){setContext(null);setError('Chưa kết nối máy chủ local.');}}
    }
    void refresh();const timer=setInterval(()=>void refresh(),7000);
    return()=>{alive=false;controller.abort();clearInterval(timer);};
  },[device?.id,device?.direction,device?.partner_batch_id]);
  useEffect(()=>{stop();setState({phase:'scanning',feedback:'Nhìn thẳng và giữ yên. Camera sẽ tự nhận diện.'});},[device?.id,device?.direction,context?.batch.id]);
  useEffect(()=>{
    const key='partner-announced:'+(device?.id||'unpaired');let ids:string[]=[];
    try{const parsed=JSON.parse(sessionStorage.getItem(key)||'[]');if(Array.isArray(parsed))ids=parsed.filter(value=>typeof value==='string');}catch{/* Keep an in-memory event guard. */}
    announcement.current=new KioskAnnouncement(ids,values=>{try{sessionStorage.setItem(key,JSON.stringify(values));}catch{/* Recognition does not depend on audio history. */}});
  },[device?.id]);
  useEffect(()=>{
    const receipt=state.receipt;if(!receipt)return;
    void announcement.current?.announce({...receipt,employee_code:receipt.worker_code,employee_name:receipt.worker_name},async()=>{
      try{await audioCue.current?.play();setAudioMessage('');}catch{setAudioMessage('Trình duyệt chưa phát được âm thanh. Bấm Bật âm thanh và kiểm tra âm lượng thiết bị.');}
    });
  },[state.receipt]);
  useEffect(()=>{
    const key=state.worker?.id||'';
    if(key!==lastWorker.current){lastWorker.current=key;cancelVoice();setName(state.worker?.name||'');setSource('manual');setVoiceMessage('');}
  },[state.worker?.id]);
  useEffect(()=>{
    if(!camera||!video.current||['name','expired'].includes(state.phase))return;
    return startLocalFaceTracker(video.current,setBoxes);
  },[camera,state.phase]);
  useEffect(()=>{
    if(!camera||!device?.id||!context?.recording_enabled)return;
    const key='partner-pending:'+device.id;
    try{
      const controller=new PartnerFlow({request,photo:async()=>{if(!video.current)throw new Error('Camera chưa sẵn sàng.');return fullFramePhoto(video.current);},
        load:()=>sessionStorage.getItem(key),save:id=>{if(id)sessionStorage.setItem(key,id);else sessionStorage.removeItem(key);},
        loadWorker:()=>sessionStorage.getItem(key+':worker'),saveWorker:id=>{if(id)sessionStorage.setItem(key+':worker',id);else sessionStorage.removeItem(key+':worker');},
        uuid:()=>crypto.randomUUID(),now:()=>performance.now(),update:setState});
      flow.current=controller;void controller.step();const timer=setInterval(()=>void controller.step(),500);
      return()=>{clearInterval(timer);controller.stop();if(flow.current===controller)flow.current=null;};
    }catch{setError('Cho phép lưu dữ liệu của trang để giữ mã yêu cầu, rồi bật lại camera.');}
  },[camera,device?.id,device?.direction,context?.batch.id,context?.recording_enabled]);
  async function start(){
    stop();const current=generation.current;setStarting(true);setError('');
    unlockAudio();
    cameraOwner.current?.claim();
    try{
      if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera cần localhost hoặc HTTPS tin cậy.');
      await new Promise(resolve=>setTimeout(resolve,200));
      if(current!==generation.current)return;
      const media=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:1280},height:{ideal:720}},audio:false});
      if(current!==generation.current||!video.current){media.getTracks().forEach(track=>track.stop());return;}
      stream.current=media;video.current.srcObject=media;await video.current.play();
      if(current===generation.current)setCamera(true);else media.getTracks().forEach(track=>track.stop());
    }catch(e){if(current===generation.current){stop();setError(e instanceof DOMException&&e.name==='NotReadableError'?'Camera đang được tab hoặc ứng dụng khác sử dụng. Tắt camera ở cửa sổ cũ rồi bật lại tại đây.':e instanceof Error?e.message:'Chưa mở được camera.');}}
    finally{if(current===generation.current)setStarting(false);}
  }
  useEffect(()=>{
    if(!context?.recording_enabled||!device?.paired)return;
    const key=`${device.id}:${device.direction}:${context.batch.id}`;if(auto.current===key)return;
    auto.current=key;void start();
  },[context?.batch.id,context?.recording_enabled,device?.id,device?.paired,device?.direction]);
  useEffect(()=>{if(context&&!context.recording_enabled){auto.current='';stop();}},[context?.recording_enabled]);
  useEffect(()=>{
    const visibility=()=>{if(document.hidden)stop();};document.addEventListener('visibilitychange',visibility);
    return()=>{document.removeEventListener('visibilitychange',visibility);generation.current++;flow.current?.stop();requests.current.forEach(controller=>controller.abort());stream.current?.getTracks().forEach(track=>track.stop());voiceGeneration.current++;recorder.current.cancel();voiceAbort.current?.abort();};
  },[]);
  async function readName(){
    const worker=state.worker;if(!worker||!camera)return;
    cancelVoice();const current=voiceGeneration.current;const revision=worker.name_revision;setVoice('starting');setVoiceMessage('');
    try{
      const blob=await recorder.current.record(()=>{if(current===voiceGeneration.current)setVoice('recording');});
      if(current!==voiceGeneration.current)return;setVoice('processing');
      const controller=new AbortController();voiceAbort.current=controller;const timeout=setTimeout(()=>controller.abort(),40000);
      try{
        const response=await fetch(`/api/kiosk/partners/workers/${worker.id}/speech?expected_revision=${revision}`,{method:'POST',body:blob,signal:controller.signal,headers:{'Content-Type':blob.type,'X-Kiosk-Intent':'transcribe-partner-name'}});
        const body=await response.json();if(current!==voiceGeneration.current)return;
        if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Chưa nhận rõ họ tên; vui lòng nhập tay.');
        if(body.worker_id!==worker.id||body.expected_revision!==revision)throw new Error('Phiên đọc đã thay đổi. Vui lòng nhập tay.');
        setName(body.draft);setSource('voice');setVoiceMessage('Kiểm tra dấu và chính tả; sửa nếu cần rồi xác nhận.');
      }finally{clearTimeout(timeout);if(voiceAbort.current===controller)voiceAbort.current=null;}
    }catch(e){if(current===voiceGeneration.current)setVoiceMessage(e instanceof DOMException&&e.name==='NotAllowedError'?'Micro chưa được cấp quyền. Chọn “Nhập bằng tay” để tiếp tục.':e instanceof Error?e.message:'Chưa nhận rõ họ tên; vui lòng nhập tay.');}
    finally{if(current===voiceGeneration.current)setVoice('idle');}
  }
  async function confirm(){
    if(!state.worker||!flow.current||!name.trim())return;
    unlockAudio();
    cancelVoice();setNameBusy(true);setVoiceMessage('');
    try{await flow.current.confirmName(state.worker.id,name.trim(),source,state.worker.name_revision);}
    catch(e){setVoiceMessage(e instanceof Error?e.message:'Chưa xác nhận được họ tên.');}
    finally{setNameBusy(false);}
  }
  const shown=(boxes??(state.faceBox?[state.faceBox]:[])).map(mirrorFaceBox).filter(box=>box!==null);
  const worker=state.worker,receipt=state.receipt;
  const canStart=!!context?.recording_enabled&&!!device?.paired;
  async function testSound(){unlockAudio();try{await audioCue.current?.play();setAudioMessage('');}catch{setAudioMessage('Chưa phát được âm thanh. Kiểm tra âm lượng và quyền âm thanh của trình duyệt.');}}
  return <section className="partner-terminal" aria-label="Chấm công đối tác">
    <div className="partner-terminal-heading"><div><span className="eyebrow">CHẤM CÔNG ĐỐI TÁC</span><h2>{context?.partner.name||'Chưa gán đợt đối tác'}</h2><p>{context?`${context.batch.name} · ${context.batch.site}`:'Gán thiết bị cho đợt tại Quản trị → Chấm công đối tác.'}</p></div><button className="secondary" onClick={()=>setOptions(value=>!value)} aria-expanded={options}>⚙ Tùy chọn</button></div>
    <div className="partner-directions" aria-label="Chiều chấm công">{(['in','out'] as const).map(direction=><button key={direction} disabled={!context||!device?.paired||directionBusy||device.direction===direction} className={device?.direction===direction?'selected':''} onClick={()=>{unlockAudio();stop();onDirectionChange(direction);}}>{direction==='in'?'→ Vào ca':'← Ra ca'}</button>)}</div>
    {options&&<div className="partner-options"><button className="secondary" disabled={starting||(!camera&&!canStart)} onClick={()=>camera?stop():void start()}>{camera?'Tắt camera':'Bật camera'}</button><button className="secondary" onClick={()=>setPairing(value=>!value)}>Ghép thiết bị</button><button className="secondary" onClick={()=>void testSound()}>Thử giọng đọc</button>{pairing&&<PairingPanel onDevice={onDeviceChange} initiallyOpen allowRePair/>}</div>}
    <div className="partner-camera" style={{aspectRatio:aspect}}><video ref={video} autoPlay playsInline muted onLoadedMetadata={()=>{if(video.current?.videoWidth)setAspect(video.current.videoWidth/video.current.videoHeight);}}/>{camera&&shown.map((box,index)=><span key={index} className="partner-face-box" style={box}/>)}{!camera&&<div className="partner-camera-idle"><strong>Camera đối tác</strong><button className="primary" disabled={starting||!canStart} onClick={()=>void start()}>{starting?'Đang mở…':'Bật camera'}</button></div>}</div>
    {error&&<p className="error" role="alert">{error}</p>}
    <div className={`partner-result ${receipt?'has-receipt':''}`} aria-live="polite"><strong>{camera?state.feedback:'Camera đang tắt. Bật camera để quét tự động.'}</strong>{receipt&&<><h3>{receipt.worker_name}</h3><p>{receipt.worker_code} · {receipt.direction==='in'?'Vào':'Ra'} · {new Date(receipt.server_time).toLocaleTimeString('vi-VN',{timeZone:context?.batch.timezone||'Asia/Ho_Chi_Minh'})}</p></>}{worker&&worker.state==='pending'&&<p>Mã tạm: <strong>{worker.code}</strong> · Hết phiên lúc {new Date(worker.pending_expires_at).toLocaleTimeString('vi-VN')}</p>}</div>
    {camera&&worker&&['pending','expired'].includes(worker.state)&&<PartnerNameDialog worker={worker} phase={state.phase} name={name} voice={voice} busy={nameBusy} message={voiceMessage} feedback={state.feedback} stream={stream.current}
      onName={value=>{cancelVoice();setName(value);setSource(source==='voice'||source==='voice_edited'?'voice_edited':'manual');}}
      onRead={()=>void readName()} onStopRead={()=>recorder.current.finish()}
      onManual={()=>{cancelVoice();setVoiceMessage('');}} onConfirm={()=>void confirm()}
      onCancel={()=>{cancelVoice();flow.current?.cancel();}}/>}
    {audioMessage&&<div role="status"><p>{audioMessage}</p><button className="secondary" onClick={()=>void testSound()}>Bật âm thanh và nghe thử</button></div>}
    {context?.batch.rules.functional_trial&&<p className="partner-privacy">Đang chạy thử chức năng. Chưa nghiệm thu độ chính xác theo nhóm hoặc chống ảnh giả; dữ liệu thử không dùng làm chứng từ thanh toán.</p>}
    <p className="partner-privacy">Mẫu mặt chỉ dùng cho ca/đợt này và hết hạn 48 giờ sau khi kết thúc ca. Họ tên và lượt Vào/Ra được giữ để đối soát. Giọng nói không lưu lại; bạn luôn có thể nhập họ tên bằng tay.</p>
    <audio ref={audio} preload="auto" src="/audio/hop-le-user-fast-135.wav"/>
  </section>;
}
