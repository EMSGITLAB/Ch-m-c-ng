import assert from 'node:assert/strict';
import test from 'node:test';
import { mirrorFaceBox, sceneLayout } from '../src/faceTracking.ts';

test('detector coordinates follow mirrored preview without imposing an oval or centre',()=>{
  const box=mirrorFaceBox([.1,.2,.25,.3]);
  assert.equal(Number.parseFloat(box.left),65);assert.equal(box.top,'20%');
  assert.equal(box.width,'25%');assert.equal(box.height,'30%');
  assert.equal(mirrorFaceBox([0,0,.1,.1]).left,'90%');
  assert.ok(mirrorFaceBox([.8,.8,.2,.2]));
});
test('invalid or absent detector boxes never produce visible face markers',()=>{
  for(const value of [null,undefined,[],[NaN,0,.2,.2],[-.1,0,.2,.2],[0,0,0,.2],[.9,0,.2,.2],[0,0,1,Infinity]])assert.equal(mirrorFaceBox(value),null);
});


test('full-scene preview preserves aspect and face coordinates in landscape and portrait cards',()=>{
  const wide=sceneLayout(800,400,4/3);
  assert.ok(Math.abs(parseFloat(wide.height)-400)<1e-9);
  assert.ok(Math.abs(parseFloat(wide.width)/parseFloat(wide.height)-4/3)<1e-12);
  assert.ok(parseFloat(wide.left)>0);
  const tall=sceneLayout(600,500,16/9);
  assert.equal(parseFloat(tall.width),600);
  assert.equal(parseFloat(tall.top),(500-600/(16/9))/2);
  assert.deepEqual(sceneLayout(0,0,16/9),{});
});
