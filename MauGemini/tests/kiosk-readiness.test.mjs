import assert from 'node:assert/strict';
import test from 'node:test';
import { kioskReadiness } from '../src/kioskReadiness.ts';

const server={recognition_ready:true,attendance_enabled:true};
const paired={active:true,paired:true};

test('local face tracking never implies attendance permission for an unpaired browser',()=>{
  for(const device of [null,{active:true,paired:false},{active:false,paired:true}]) {
    const result=kioskReadiness(server,device);
    assert.equal(result.code,'unpaired');assert.equal(result.canRecord,false);
    assert.match(result.title,/Chưa ghép/);assert.match(result.feedback,/chỉ định vị/);
  }
});

test('server disconnection, model readiness and stopped attendance stay explicit',()=>{
  assert.equal(kioskReadiness(null,paired).code,'offline');
  assert.equal(kioskReadiness({...server,recognition_ready:false},paired).code,'loading');
  const paused=kioskReadiness({...server,attendance_enabled:false},paired);
  assert.equal(paused.code,'paused');assert.equal(paused.canRecord,false);
});

test('pairing restores readiness and revocation immediately removes it',()=>{
  assert.equal(kioskReadiness(server,null).canRecord,false);
  assert.equal(kioskReadiness(server,paired).canRecord,true);
  assert.equal(kioskReadiness(server,{...paired,active:false}).canRecord,false);
  assert.equal(kioskReadiness(server,paired).code,'ready');
});
