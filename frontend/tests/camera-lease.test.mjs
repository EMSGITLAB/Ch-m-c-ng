import test from 'node:test';
import assert from 'node:assert/strict';
import { connectCameraOwner } from '../src/cameraLease.ts';

test('new camera owner releases an older OnTime tab without sharing media or credentials',()=>{
  const listeners=new Set(),messages=[];
  const channel=()=>({addEventListener:(name,callback)=>listeners.add(callback),removeEventListener:(name,callback)=>listeners.delete(callback),postMessage:value=>{messages.push(value);for(const callback of listeners)callback({data:value});},close:()=>{}});
  let firstStops=0,secondStops=0;
  const first=connectCameraOwner(()=>firstStops++,channel());
  const second=connectCameraOwner(()=>secondStops++,channel());
  second.claim();assert.equal(firstStops,1);assert.equal(secondStops,0);
  first.claim();assert.equal(firstStops,1);assert.equal(secondStops,1);
  assert.deepEqual(Object.keys(messages[0]).sort(),['owner','type']);
  second.close();first.claim();assert.equal(secondStops,1);
  first.close();assert.equal(listeners.size,0);
});

test('lack of BroadcastChannel does not block the local camera fallback',()=>{
  let stopped=0;const owner=connectCameraOwner(()=>stopped++,null);owner.claim();owner.close();assert.equal(stopped,0);
});
