import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import './admin.css';
import { AdminPanel } from './AdminPanel';
import { PairingPanel, type KioskDevice } from './PairingPanel';
import { KioskCapture, type KioskStatus } from './KioskCapture';

function App(){
 const [status,setStatus]=useState<KioskStatus|null>(null);
 const [now,setNow]=useState(new Date());
 const [view,setView]=useState<'kiosk'|'admin'>(location.hash==='#admin'?'admin':'kiosk');
 const [device,setDevice]=useState<KioskDevice|null>(null);
 const serverClock=useRef<{at:number;received:number}|null>(null);
 useEffect(()=>{
  let disposed=false,pending:AbortController|null=null;
  const check=async()=>{pending?.abort();const request=new AbortController();pending=request;const timeout=setTimeout(()=>request.abort(),6000);try{const response=await fetch('/api/system/status',{signal:request.signal});if(!response.ok)throw new Error();const body=await response.json();const at=Date.parse(body.server_time);if(!Number.isFinite(at))throw new Error();if(!disposed&&pending===request){serverClock.current={at,received:performance.now()};setNow(new Date(at));setStatus(body);}}catch{if(!disposed&&pending===request)setStatus(null);}finally{clearTimeout(timeout);}};
  void check();const poll=setInterval(check,10000),clock=setInterval(()=>{const anchor=serverClock.current;if(anchor)setNow(new Date(anchor.at+performance.now()-anchor.received));},1000);
  const hash=()=>setView(location.hash==='#admin'?'admin':'kiosk');window.addEventListener('hashchange',hash);
  return()=>{disposed=true;pending?.abort();clearInterval(poll);clearInterval(clock);window.removeEventListener('hashchange',hash);};
 },[]);
 const timezone=status?.timezone||'Asia/Ho_Chi_Minh';
 const hour=Number(new Intl.DateTimeFormat('en-GB',{hour:'2-digit',hourCycle:'h23',timeZone:timezone}).format(now));
 const greeting=hour<11?'Chào buổi sáng!':hour<14?'Chào buổi trưa!':hour<18?'Chào buổi chiều!':'Chào buổi tối!';
 function changeView(next:'kiosk'|'admin'){setView(next);location.hash=next==='admin'?'admin':'kiosk';}
 return <div className={`shell ${view==='kiosk'?'terminal-shell':''}`}>
  <header><a className="brand" href="/"><span className="mark">C</span><span>Chấm công<span className="brand-sub">Không gian làm việc nội bộ</span></span></a><nav className="view-nav" aria-label="Điều hướng ứng dụng"><button className={view==='kiosk'?'selected':''} onClick={()=>changeView('kiosk')}>Chấm công</button><button className={view==='admin'?'selected':''} onClick={()=>changeView('admin')}>Quản trị</button></nav><span className="connection"><i className={status?'online':''}/>{status?'Máy chủ local đã kết nối':'Chưa kết nối được máy chủ'}</span></header>
  {view==='admin'?<AdminPanel/>:<main className="terminal-main">
   <section className="intro terminal-clock"><span className="eyebrow">ĐIỂM CHẤM CÔNG</span><h1>{greeting}</h1><div className="clock">{status?now.toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',timeZone:timezone}):'--:--'}<span>{now.toLocaleDateString('vi-VN',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:timezone})}</span><small>Giờ máy chủ · Việt Nam</small></div><p>Nhìn về camera<br/>và giữ yên trong giây lát.</p><div className="terminal-device"><span className={`terminal-led ${status?'online':''}`}/>{device?.paired?(device.direction==='in'?'Điểm vào ca':'Điểm ra ca'):'Chờ ghép thiết bị'}</div><div className="privacy"><span>◈</span><p>Xử lý tại máy chủ nội bộ.<br/>Không cần Internet.</p></div></section>
   <KioskCapture status={status} device={device}/>
  </main>}
  {view==='kiosk'&&<PairingPanel onDevice={setDevice}/>}
  <div className="notice" role="status"><span className="notice-dot"/><p>{status?.message||'Chưa kết nối được máy chủ. Chưa xác nhận bất kỳ lượt chấm công nào.'}</p></div>
  <footer><span>CHẤM CÔNG LOCAL{device?' · '+device.name:''}</span><span>Phiên bản {status?.version||'0.2.0'} · {timezone}</span></footer>
 </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
