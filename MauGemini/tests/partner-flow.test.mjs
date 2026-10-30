import test from 'node:test';
import assert from 'node:assert/strict';
import { PartnerFlow } from '../src/partnerFlow.ts';
import { KioskError } from '../src/kioskFlow.ts';
import { LocalNameRecorder, recordingMime } from '../src/LocalNameRecorder.ts';

const worker={id:'worker1',code:'D23-C0001-00001',name:null,state:'pending',name_revision:0,name_confirmed:false,admission_approved:false,pending_expires_at:'2026-10-30T06:02:00Z',in_at:null,out_at:null};
const receipt={status:'recorded',request_id:'id1',event_id:'event1',worker_id:'worker1',worker_code:worker.code,worker_name:'Nguyễn Văn Thử',direction:'in',server_time:'2026-10-30T06:00:00Z',batch_id:'batch1'};
function fixture({initial=null,pendingWorker=null,face=true,person={...worker},lostCommit=false,lostName=false,direction='in'}={}){
  let saved=initial,savedWorker=pendingWorker,number=0,now=0,capture=null,commits=0,lost=lostCommit;const calls=[];
  const ports={
    request:async(path,options={})=>{
      calls.push({path,options});
      if(path.endsWith('/preview'))return {ready:face,face_present:face,feedback:'Giữ yên'};
      if(path.endsWith('/captures')&&options.method==='POST'){capture={request_id:JSON.parse(options.body).request_id,state:'pending',next_frame_index:1,capture_nonce:'nonce'};return {...capture};}
      if(path.includes('/frames/')){capture={...capture,state:'verified',worker:{...person},owned_enrollment:true};return {...capture};}
      if(path.endsWith('/name')){const payload=JSON.parse(options.body);person={...person,name:payload.name,name_source:payload.source,name_revision:person.name_revision+1,name_confirmed:true,admission_approved:true};capture={...capture,state:'rejected'};if(lostName){lostName=false;throw new Error('name response lost');}return {...person};}
      if(path.endsWith('/cancel')){person.state='cancelled';return {...person};}
      if(path.includes('/workers/')&&!options.method)return {...person};
      if(path.endsWith('/commit')){
        commits++;const result={...receipt,request_id:capture.request_id,direction};capture={...capture,state:'used',receipt:result};
        if(lost){lost=false;throw new Error('response lost');}return result;
      }
      if(path.includes('/captures/')){if(!capture)throw new KioskError(404,'not created');return {...capture};}
      throw new Error('Unexpected '+path);
    },photo:async()=>new Blob(['photo']),load:()=>saved,save:id=>{saved=id;},loadWorker:()=>savedWorker,saveWorker:id=>{savedWorker=id;},uuid:()=>`id${++number}`,now:()=>now,update:()=>{},
  };
  const flow=new PartnerFlow(ports);
  return {flow,calls,ports,get saved(){return saved;},get savedWorker(){return savedWorker;},get commits(){return commits;},advance:()=>{now+=2000;},expire:()=>{person.state='expired';}};
}
async function steps(env,count=1){for(let i=0;i<count;i++){env.advance();await env.flow.step();await new Promise(done=>setImmediate(done));}}

test('partner kiosk creates no capture without a face',async()=>{
  const env=fixture({face:false});await steps(env,4);assert.equal(env.saved,null);assert.ok(env.calls.every(c=>c.path.endsWith('/preview')));
});
test('name confirmation automatically proceeds to a fresh same-face proof and the first punch',async()=>{
  const env=fixture();await steps(env,2);assert.equal(env.flow.state.phase,'name');assert.equal(env.commits,0);
  const confirming=env.flow.confirmName(worker.id,'Nguyễn Văn Thử','manual',0);
  await steps(env,2);await confirming;assert.equal(env.flow.state.phase,'verifying');assert.equal(env.commits,0);
  const names=env.calls.filter(c=>c.path.endsWith('/name'));assert.equal(names.length,1);assert.equal(JSON.parse(names[0].options.body).expected_revision,0);
  await steps(env,4);assert.equal(env.commits,1);assert.equal(env.flow.state.feedback,'Hợp lệ');assert.equal(env.saved,null);
  assert.ok(env.calls.every(call=>!call.path.includes('/approve')));
});
test('lost commit response retains request and recovers the one durable receipt',async()=>{
  const env=fixture({person:{...worker,state:'active',name:'Nguyễn Văn Thử',name_confirmed:true,admission_approved:true},lostCommit:true});
  await steps(env,2);assert.equal(env.commits,1);assert.equal(env.saved,'id1');
  await steps(env);assert.equal(env.flow.state.phase,'success');assert.equal(env.saved,null);assert.equal(env.commits,1);
  await steps(env,4);assert.equal(env.commits,1);assert.equal(env.calls.filter(c=>c.path.endsWith('/captures')).length,1);
});
test('reload retries the saved request ID when creation response was lost',async()=>{
  const env=fixture({initial:'saved-request',person:{...worker,state:'active'}});
  await steps(env,2);const creates=env.calls.filter(c=>c.path.endsWith('/captures'));assert.equal(creates.length,1);assert.equal(JSON.parse(creates[0].options.body).request_id,'saved-request');
});
test('late name command cannot apply to a different worker',async()=>{
  const env=fixture();await steps(env,2);
  const promise=env.flow.confirmName('old-worker','Tên cũ','voice',0).catch(error=>error);
  await steps(env,3);assert.match((await promise).message,/thay đổi/);assert.equal(env.calls.filter(c=>c.path.endsWith('/name')).length,0);assert.equal(env.commits,0);
});
test('stopping during face preview does not create a new admission',async()=>{
  const env=fixture();let resolve;env.ports.request=()=>new Promise(done=>{resolve=done;});
  const pending=env.flow.step();await new Promise(done=>setImmediate(done));env.flow.stop();resolve({ready:true});await pending;assert.equal(env.saved,null);
});
test('micro supports Safari mp4 and keeps manual fallback independent',()=>{
  assert.equal(recordingMime({isTypeSupported:value=>value==='audio/mp4'}),'audio/mp4');
  assert.equal(recordingMime({isTypeSupported:()=>false}),undefined);
});
test('late microphone permission after cancel releases every track',async()=>{
  const descriptor=Object.getOwnPropertyDescriptor(globalThis,'navigator'),oldRecorder=globalThis.MediaRecorder;
  let resolve,stopped=0;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:()=>new Promise(done=>{resolve=done;})}}});
  globalThis.MediaRecorder={isTypeSupported:()=>true};
  try{
    const recorder=new LocalNameRecorder();const pending=recorder.record(()=>{}).catch(error=>error);recorder.cancel();resolve({getTracks:()=>[{stop:()=>stopped++}]});
    assert.match((await pending).message,/thay đổi/);assert.equal(stopped,1);
  }finally{if(descriptor)Object.defineProperty(globalThis,'navigator',descriptor);else delete globalThis.navigator;globalThis.MediaRecorder=oldRecorder;}
});

test('name popup holds the one person and sends no photos or new captures while typing',async()=>{
  const env=fixture();await steps(env,2);const images=env.calls.filter(call=>/preview|frames|\/captures$/.test(call.path)).length;
  await steps(env,35);
  assert.equal(env.flow.state.phase,'name');assert.equal(env.savedWorker,worker.id);
  assert.equal(env.calls.filter(call=>/preview|frames|\/captures$/.test(call.path)).length,images);
  assert.equal(env.commits,0);
});
test('reload resumes the held name popup without scanning or reserving anyone else',async()=>{
  const env=fixture({pendingWorker:worker.id});await steps(env,3);
  assert.equal(env.flow.state.phase,'name');assert.equal(env.calls.length,3);
  assert.ok(env.calls.every(call=>call.path.endsWith('/workers/'+worker.id)));
});
test('confirming the popup pins all new face proofs to the same worker',async()=>{
  const env=fixture();await steps(env,2);
  const confirming=env.flow.confirmName(worker.id,'Nguyễn Văn Thử','manual',0);
  await steps(env,4);await confirming;
  const create=env.calls.filter(call=>call.path.endsWith('/captures'));
  assert.equal(create.length,3);assert.ok(create.slice(1).every(call=>JSON.parse(call.options.body).expected_worker_id===worker.id));
  assert.equal(env.flow.state.phase,'success');
});
test('lost name confirmation is recovered from the held person without writing a second name',async()=>{
  const env=fixture({lostName:true});await steps(env,2);
  const confirming=env.flow.confirmName(worker.id,'Nguyễn Văn Thử','manual',0);
  await steps(env,6);await confirming;
  assert.equal(env.flow.state.phase,'success');assert.equal(env.calls.filter(call=>call.path.endsWith('/name')).length,1);
  assert.equal(env.savedWorker,null);assert.equal(env.commits,1);
});
test('expired popup stays explicit and never silently allocates another code',async()=>{
  const env=fixture();await steps(env,2);env.expire();await steps(env,8);
  assert.equal(env.flow.state.phase,'expired');assert.equal(env.savedWorker,worker.id);
  assert.equal(env.calls.filter(call=>call.path.endsWith('/captures')).length,1);
});
test('a previously confirmed held session resumes automatically without waiting for approval',async()=>{
  const env=fixture({pendingWorker:worker.id,person:{...worker,name:'Nguyễn Văn Thử',name_confirmed:true,name_revision:1,admission_approved:false}});
  await steps(env,4);
  assert.equal(env.commits,1);assert.equal(env.flow.state.phase,'success');
  assert.equal(env.calls.filter(call=>call.path.endsWith('/name')).length,0);
  assert.ok(env.calls.every(call=>!call.path.includes('/approve')));
  const create=env.calls.find(call=>call.path.endsWith('/captures'));
  assert.equal(JSON.parse(create.options.body).expected_worker_id,worker.id);
});
test('cancelling the popup releases the held code without immediately reenrolling the same face',async()=>{
  const env=fixture();await steps(env,2);env.flow.cancel();await steps(env,5);
  assert.equal(env.savedWorker,null);assert.equal(env.calls.filter(call=>call.path.endsWith('/captures')).length,1);assert.equal(env.commits,0);
});
