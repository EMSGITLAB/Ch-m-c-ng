import assert from 'node:assert/strict';
import test from 'node:test';
import { runPadTrial } from '../src/padTrial.ts';

const observation=()=>({quality_accepted:true,server_time:'2026-10-28T01:00:00Z',stored:false,attendance_recorded:false,pad:{model_id:'pad',ensemble_live_score:.7,pad_ms:12,decision:'not_evaluated',validated_for_attendance:false,models:[{context_clipped:false}]}});
const ports=()=>({photo:async()=>new Blob(['test']),preview:async()=>observation(),current:()=>true,pause:async()=>{},update:()=>{}});
test('five frames report one correlated session without inventing a PAD verdict',async()=>{
  const result=await runPadTrial(ports());
  assert.equal(result.captured_frames,5);assert.equal(result.quality_accepted_frames,5);
  assert.ok(Math.abs(result.live_score_mean-.7)<1e-6);assert.equal(result.threshold,null);
  assert.equal(result.validated_for_attendance,false);assert.equal(result.decision,'not_evaluated');
});
test('poor quality frames stay explicit and do not contribute fabricated zero or positive scores',async()=>{
  const p=ports();p.preview=async()=>({...observation(),quality_accepted:false,pad:null,reason:'no_face'});
  const result=await runPadTrial(p);assert.equal(result.quality_accepted_frames,0);assert.equal(result.live_score_mean,null);
});
test('stop during photo encoding sends no image and stop during pause stops the sequence',async()=>{
  const p=ports();let current=true,calls=0;p.current=()=>current;
  p.photo=async()=>{current=false;return new Blob(['late']);};p.preview=async()=>{calls++;return observation();};
  await assert.rejects(runPadTrial(p),{name:'AbortError'});assert.equal(calls,0);
  const q=ports();q.current=()=>current;current=true;q.pause=async()=>{current=false;};q.preview=async()=>{calls++;return observation();};
  await assert.rejects(runPadTrial(q),{name:'AbortError'});assert.equal(calls,1);
});
test('non-finite scores, model switches and claims of validation are rejected',async()=>{
  for(const change of [{ensemble_live_score:NaN},{validated_for_attendance:true},{decision:'passed'}]){
    const p=ports();p.preview=async()=>({...observation(),pad:{...observation().pad,...change}});
    await assert.rejects(runPadTrial(p),/hợp lệ/);
  }
  const p=ports();let counter=0;p.preview=async()=>({...observation(),pad:{...observation().pad,model_id:String(counter++)}});
  await assert.rejects(runPadTrial(p),/thay đổi/);
});
