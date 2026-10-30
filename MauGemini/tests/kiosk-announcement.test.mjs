import assert from 'node:assert/strict';
import test from 'node:test';
import { KioskAnnouncement } from '../src/kioskAnnouncement.ts';

const receipt={status:'recorded',event_id:'event-1'};
test('success audio plays once per saved event, including after reload or concurrent updates',async()=>{
  let saved=[],plays=0;
  const announce=new KioskAnnouncement([],ids=>saved=ids);
  await Promise.all([announce.announce(receipt,async()=>plays++),announce.announce(receipt,async()=>plays++)]);
  assert.equal(plays,1);
  await new KioskAnnouncement(saved,()=>{}).announce(receipt,async()=>plays++);
  assert.equal(plays,1);
  await announce.announce({...receipt,event_id:'event-2'},async()=>plays++);
  assert.equal(plays,2);
});
test('duplicate attendance and failed playback never queue repeated success announcements',async()=>{
  let plays=0;const announce=new KioskAnnouncement([],()=>{});
  await announce.announce({...receipt,status:'duplicate'},async()=>plays++);assert.equal(plays,0);
  await assert.rejects(announce.announce(receipt,async()=>{plays++;throw new Error('blocked');}),/blocked/);
  await announce.announce(receipt,async()=>plays++);assert.equal(plays,1);
});
