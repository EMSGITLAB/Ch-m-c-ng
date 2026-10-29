import test from 'node:test';
import assert from 'node:assert/strict';
import { KioskFlow, KioskError } from '../src/kioskFlow.ts';

const receipt={status:'recorded',request_id:'id-1',event_id:'event-1',employee_code:'000123',employee_name:'Hồ sơ thử',server_time:'2026-10-28T01:00:00Z',direction:'in'};
function fixture(handler,initial=null){
  let saved=initial,now=0,enabled=true,number=0,photos=0;const calls=[],states=[];
  const ports={request:async(path,options={})=>{calls.push({path,options});return handler(path,options);},photo:async()=>{photos++;return new Blob([`frame-${photos}`]);},enabled:()=>enabled,load:()=>saved,save:id=>{saved=id;},uuid:()=>`id-${++number}`,now:()=>now,update:state=>states.push(state)};
  return {ports,calls,states,get saved(){return saved;},get photos(){return photos;},advance:(ms=1000)=>{now+=ms;},disable:()=>{enabled=false;}};
}

test('no face or disabled policy does not create or persist attendance requests',async()=>{
  const env=fixture(()=>({ready:false,face_present:false,feedback:'Chưa thấy mặt'}));const flow=new KioskFlow(env.ports);
  await flow.step();assert.equal(env.saved,null);assert.equal(env.calls.length,1);assert.match(env.calls[0].path,/preview$/);
  env.disable();await flow.step();assert.equal(flow.state.phase,'disabled');assert.equal(env.calls.length,2);assert.equal(env.saved,null);
});

test('disabled recording still detects moving faces automatically without starting attendance',async()=>{
  let box=[.1,.2,.2,.3];
  const env=fixture(()=>({ready:true,face_present:true,face_box:box,feedback:'Đã thấy mặt'}));env.disable();
  const flow=new KioskFlow(env.ports);
  await flow.step();assert.deepEqual(flow.state.faceBox,box);assert.equal(env.saved,null);
  box=[.5,.2,.2,.3];await flow.step();assert.deepEqual(flow.state.faceBox,box);
  assert.equal(env.photos,2);assert.ok(env.calls.every(call=>call.path.endsWith('/preview')));
  assert.equal(flow.state.receipt,undefined);
});

test('full sequence waits for supervisor and shows only committed receipt',async()=>{
  let frames=0,confirmed=false,commits=0;
  const env=fixture((path,options)=>{
    if(path.endsWith('/preview'))return {ready:true,face_present:true};
    if(path.endsWith('/sessions')&&options.method==='POST'){assert.equal(env.saved,'id-1');return {request_id:'id-1',state:'pending'};}
    if(path.includes('/frames/')){frames++;return {state:frames===3?'verified':'pending',stable_frames:frames,feedback:'Giữ yên'};}
    if(path.endsWith('/commit')){commits++;return receipt;}
    return {request_id:'id-1',state:frames===3?'verified':'pending',needs_supervisor:!confirmed,next_frame_index:frames+1,capture_nonce:'nonce'};
  });
  const flow=new KioskFlow(env.ports);await flow.step();
  for(let index=0;index<3;index++){env.advance(500);await flow.step();}
  env.advance();await flow.step();assert.equal(flow.state.phase,'waiting');assert.equal(commits,0);assert.equal(flow.state.receipt,undefined);
  confirmed=true;env.advance();await flow.step();assert.equal(flow.state.phase,'success');assert.equal(flow.state.receipt.employee_code,'000123');assert.equal(env.saved,null);assert.equal(commits,1);
});

test('explicit automatic verification commits immediately after the final frame',async()=>{
  const calls=[];
  const env=fixture(path=>{
    calls.push(path);
    if(path.includes('/frames/'))return {state:'verified',needs_supervisor:false,stable_frames:3};
    if(path.endsWith('/commit'))return receipt;
    return {request_id:'id-1',state:'pending',next_frame_index:3,capture_nonce:'nonce'};
  },'id-1');
  const flow=new KioskFlow(env.ports);await flow.step();
  assert.equal(flow.state.phase,'success');assert.equal(env.saved,null);
  assert.equal(calls.length,3);assert.ok(calls[1].endsWith('/frames/3'));assert.ok(calls[2].endsWith('/commit'));
});

test('immediate commit lost response is recovered by the same persisted request',async()=>{
  let used=false,commits=0;
  const env=fixture(path=>{
    if(path.includes('/frames/'))return {state:'verified',needs_supervisor:false};
    if(path.endsWith('/commit')){commits++;used=true;throw new TypeError('lost commit response');}
    return {request_id:'id-1',state:used?'used':'pending',next_frame_index:3,capture_nonce:'nonce',receipt:used?receipt:null};
  },'id-1');
  const flow=new KioskFlow(env.ports);await flow.step();assert.equal(env.saved,'id-1');assert.notEqual(flow.state.phase,'success');
  env.advance();await flow.step();assert.equal(flow.state.phase,'success');assert.equal(commits,1);assert.equal(env.saved,null);
});

test('final frame never shortcuts supervisor, missing permission or stopped recording',async()=>{
  for(const permission of [true,undefined,false]){
    let commits=0;
    const env=fixture(path=>{
      if(path.includes('/frames/')){if(permission===false)env.disable();return {state:'verified',needs_supervisor:permission};}
      if(path.endsWith('/commit')){commits++;return receipt;}
      return {request_id:'id-1',state:'pending',next_frame_index:3,capture_nonce:'nonce'};
    },'id-1');
    const flow=new KioskFlow(env.ports);await flow.step();assert.equal(commits,0);assert.equal(env.saved,'id-1');
  }
});

test('lost commit response survives reload and policy stop without a second commit',async()=>{
  let used=false,commits=0;
  const env=fixture(path=>{
    if(path.endsWith('/commit')){commits++;used=true;throw new TypeError('connection lost');}
    return {request_id:'id-1',state:used?'used':'verified',needs_supervisor:false,receipt:used?receipt:null};
  },'id-1');
  const first=new KioskFlow(env.ports);await first.step();assert.equal(first.state.phase,'offline');assert.equal(env.saved,'id-1');first.stop();
  env.disable();const restored=new KioskFlow(env.ports);await restored.step();assert.equal(restored.state.phase,'success');assert.equal(commits,1);assert.equal(env.saved,null);
});

test('lost frame response reconciles server index before taking next image',async()=>{
  let next=1;const indices=[];
  const env=fixture((path)=>{
    if(path.includes('/frames/')){indices.push(Number(path.split('/').at(-1)));next++;if(next===2)throw new KioskError(503,'Unknown response');return {state:'pending',feedback:'Tiếp tục'};}
    return {request_id:'id-1',state:'pending',next_frame_index:next,capture_nonce:'nonce'};
  },'id-1');
  const flow=new KioskFlow(env.ports);await flow.step();assert.equal(flow.state.phase,'recovering');env.advance();await flow.step();assert.deepEqual(indices,[1,2]);assert.equal(env.saved,'id-1');assert.equal(env.photos,2);
});

test('malformed or unrelated receipt never becomes success and preserves request',async()=>{
  const env=fixture(()=>({request_id:'id-1',state:'used',receipt:{...receipt,request_id:'another-request'}}),'id-1');
  const flow=new KioskFlow(env.ports);await flow.step();assert.notEqual(flow.state.phase,'success');assert.equal(env.saved,'id-1');assert.equal(flow.state.receipt,undefined);
});

test('one in-flight operation and stop prevent late frame writes',async()=>{
  let release;const waiting=new Promise(resolve=>{release=resolve;});
  const env=fixture(()=>waiting,'id-1');const flow=new KioskFlow(env.ports);
  const first=flow.step();await flow.step();assert.equal(env.calls.length,1);flow.stop();release({request_id:'id-1',state:'pending',next_frame_index:1,capture_nonce:'nonce'});await first;assert.equal(env.photos,0);assert.equal(env.saved,'id-1');
});

test('stopping while the preview photo encodes prevents sending that image',async()=>{
  let release;
  const env=fixture(()=>({ready:true}));
  env.ports.photo=()=>new Promise(resolve=>{release=resolve;});
  const flow=new KioskFlow(env.ports),pending=flow.step();
  flow.stop();release(new Blob(['late-photo']));await pending;
  assert.equal(env.calls.length,0);assert.equal(env.saved,null);
});

test('expiry clears only expired request; overload backs off before retry',async()=>{
  let code=429;
  const env=fixture(()=>{throw new KioskError(code,'Thử lại sau');},'id-1');const flow=new KioskFlow(env.ports);
  await flow.step();await flow.step();assert.equal(env.calls.length,1);env.advance(1500);code=410;await flow.step();assert.equal(env.saved,null);assert.equal(flow.state.phase,'retry');assert.equal(flow.state.receipt,undefined);
});

test('changed kiosk authority requires explicit restart before attempting another attendance',async()=>{
  const env=fixture(()=>{throw new KioskError(401,'Quyền đã đổi');},'id-1');const flow=new KioskFlow(env.ports);
  await flow.step();env.advance(2000);await flow.step();assert.equal(flow.state.phase,'unauthorized');assert.equal(env.saved,null);assert.equal(env.calls.length,1);
});

test('success hides identity after display and requires face departure before a new session',async()=>{
  let present=true;
  const env=fixture(path=>path.includes('/sessions/')?{request_id:'id-1',state:'used',receipt}:{ready:present,face_present:present},'id-1');
  const flow=new KioskFlow(env.ports);await flow.step();assert.equal(flow.state.phase,'success');env.advance(4001);await flow.step();assert.equal(flow.state.receipt,undefined);assert.equal(env.saved,null);
  present=false;await flow.step();assert.equal(env.saved,null);assert.equal(env.calls.filter(call=>call.options.method==='POST'&&call.path.endsWith('/sessions')).length,0);
});
