import assert from 'node:assert/strict';
import test from 'node:test';
import { mirrorFaceBox } from '../src/faceTracking.ts';

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
