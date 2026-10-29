// Exercise the actual frontend controller against the isolated local load server.
import {readFile} from 'node:fs/promises';
import {createInterface} from 'node:readline';
import {isDeepStrictEqual} from 'node:util';
import {randomUUID} from 'node:crypto';
import {KioskFlow,KioskError} from '../frontend/src/kioskFlow.ts';

const port=Number(process.env.CHAMCONG_LOAD_PORT);
if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('Invalid isolated load port');
const base=`http://127.0.0.1:${port}`;
const tokens=JSON.parse(process.env.CHAMCONG_LOAD_TOKENS||'[]');
if(tokens.length!==2||!tokens.every(value=>typeof value==='string'&&value.length>=32))throw new Error('Missing disposable kiosk tokens');
const photo=await readFile(process.env.CHAMCONG_LOAD_PHOTO);

async function session(worker,standing=false){
  const begin=performance.now();let requestId=null,firstFrame=null,firstReadyPreview=null;
  let saved=null,active=null,frames=0,latestPhase='start',lastError='',flow,timer,issued=0,transportErrors=0;
  const request=async(path,options={})=>{
    latestPhase=path.includes('/frames/')?'frame':path.endsWith('/commit')?'commit':path.endsWith('/preview')?'preview':options.method==='POST'?'start':'reconcile';
    if(path.includes('/frames/')){frames++;firstFrame??=performance.now();}
    const submitted=performance.now();
    const abort=new AbortController();active=abort;const timeout=setTimeout(()=>abort.abort(),12000);
    try{
      const response=await fetch(base+path,{...options,headers:{'Content-Type':'application/json',...options.headers,Cookie:`chamcong_kiosk=${tokens[worker]}`},signal:abort.signal});
      const body=await response.json();
      if(!response.ok)throw new KioskError(response.status,typeof body.detail==='string'?body.detail:'HTTP error');
      if(path.endsWith('/preview')&&body.ready)firstReadyPreview??=submitted;
      return body;
    }catch(error){transportErrors++;lastError=error instanceof Error?error.name+': '+error.message:'HTTP failure';throw error;}
    finally{clearTimeout(timeout);if(active===abort)active=null;}
  };
  try{
    const receipt=await new Promise((resolve,reject)=>{
      const deadline=setTimeout(()=>{clearInterval(timer);flow.stop();active?.abort();reject(new Error('frontend_session_deadline'));},30000);
      flow=new KioskFlow({request,enabled:()=>true,load:()=>saved,save:value=>{saved=value;if(value)requestId=value;},
        uuid:()=>{issued++;if(requestId)throw new Error('Unexpected replacement attendance request');return randomUUID();},
        now:()=>performance.now(),photo:async()=>new Blob([photo,randomUUID()],{type:'image/jpeg'}),
        update:state=>{if(state.phase==='success'&&state.receipt){clearTimeout(deadline);if(!standing)clearInterval(timer);resolve(state.receipt);}}});
      timer=setInterval(()=>void flow.step(),500);void flow.step();
    });
    const committed=performance.now();
    if(standing)await new Promise(resolve=>setTimeout(resolve,8000));
    flow.stop();clearInterval(timer);active?.abort();
    if(firstFrame===null||firstReadyPreview===null||receipt.request_id!==requestId)throw new Error('Incomplete controller timeline');
    latestPhase='retry_commit';
    for(let index=0;index<10;index++){
      const retry=await request(`/api/kiosk/attendance/${requestId}/commit`,{method:'POST',headers:{'X-Kiosk-Intent':'record-attendance'},body:'{}'});
      if(!isDeepStrictEqual(retry,receipt))throw new Error('retry_receipt_changed');
    }
    return {request_id:requestId,event_id:receipt.event_id,status:receipt.status,
      seconds:(committed-firstReadyPreview)/1000,recognition_seconds:(committed-firstFrame)/1000,
      recognition_frames_sent:frames,request_ids_issued:issued,recovered_transport_errors:transportErrors,
      face_remained_after_success_seconds:standing?8:0,wall_seconds:(performance.now()-begin)/1000};
  }catch(error){
    flow?.stop();active?.abort();clearInterval(timer);
    return {request_id:requestId,worker,phase:latestPhase,error_type:error.name,
      error_message:(lastError||error.message).slice(0,200),wall_seconds:(performance.now()-begin)/1000};
  }
}

for await(const line of createInterface({input:process.stdin,crlfDelay:Infinity})){
  const command=JSON.parse(line);
  if(command.command!=='pair')throw new Error('Invalid load controller command');
  process.stdout.write(JSON.stringify(await Promise.all([session(0,command.standing===true),session(1,command.standing===true)]))+'\n');
}
