import assert from 'node:assert/strict';
import test from 'node:test';
import { startLocalFaceTracker } from '../src/localFaceTracker.ts';
function browserApi(t, name, value) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, {configurable:true,writable:true,value});
  t.after(()=>{if(previous)Object.defineProperty(globalThis,name,previous);else delete globalThis[name];});
}

test('visual tracking has one frame in flight and stops its worker without touching recognition', async t => {
  let worker, scheduled, posted = [], closed = 0;
  t.mock.method(globalThis, 'setTimeout', () => 1);
  t.mock.method(globalThis, 'clearTimeout', () => {});
  browserApi(t, 'requestAnimationFrame', () => { return 1; });
  // RAF and Worker are browser APIs: provide only the public boundary, not detector internals.
  globalThis.requestAnimationFrame = callback => { scheduled = callback; return 1; };
  browserApi(t, 'cancelAnimationFrame', () => {});
  browserApi(t, 'createImageBitmap', async () => ({close() { closed++; }}));
  browserApi(t, 'Worker', class {
    constructor(url) { assert.equal(url, '/vision/tracker-worker.js'); worker = this; }
    postMessage(message) { posted.push(message); }
    terminate() { this.stopped = true; }
  });
  const video = {readyState: 4, currentTime: 1, videoWidth: 1280, videoHeight: 720};
  const boxes = [];
  const stop = startLocalFaceTracker(video, value => boxes.push(value));
  assert.equal(posted[0].type, 'init');
  worker.onmessage({data: {type: 'ready'}});
  await scheduled(100);
  video.currentTime = 2;
  await scheduled(300);
  assert.equal(posted.filter(x=>x.type==='frame').length, 1, 'never queue frames behind a busy worker');
  worker.onmessage({data: {type:'result', boxes:[[.1,.1,.2,.2]]}});
  assert.deepEqual(boxes, [[[.1,.1,.2,.2]]]);
  await scheduled(400);
  assert.equal(posted.filter(x=>x.type==='frame').length, 2);
  stop(); assert.equal(worker.stopped, true);
  assert.equal(closed, 0, 'transferred images belong to the worker');
});

test('an unsupported browser falls back to server boxes', t => {
  browserApi(t, 'Worker', class {constructor(){throw Error('unsupported');}});
  const updates = [];
  const stop = startLocalFaceTracker({}, value => updates.push(value));
  assert.deepEqual(updates, [null]);
  assert.doesNotThrow(stop);
});
