import assert from 'node:assert/strict';
import test from 'node:test';
import { centerCrop, fullFrameSize, fullFramePhoto } from '../src/cameraCapture.ts';

test('16:9 video uses the same centre crop as a 4:3 preview', () => {
  assert.deepEqual(centerCrop(1280, 720), { x: 160, y: 0, width: 960, height: 720 });
});
test('portrait camera crops vertically without distortion', () => {
  assert.deepEqual(centerCrop(720, 1280), { x: 0, y: 370, width: 720, height: 540 });
});
test('4:3 input stays complete and an unready camera cannot capture', () => {
  assert.deepEqual(centerCrop(640, 480), { x: 0, y: 0, width: 640, height: 480 });
  assert.throws(() => centerCrop(0, 0), /Camera/);
});

test('attendance preserves full landscape and portrait field of view without upscaling', () => {
  assert.deepEqual(fullFrameSize(1280,720), {width:1280,height:720});
  assert.deepEqual(fullFrameSize(1080,1920), {width:720,height:1280});
  assert.deepEqual(fullFrameSize(1920,1080), {width:1280,height:720});
  assert.deepEqual(fullFrameSize(1920,1080,1600), {width:1600,height:900});
  assert.deepEqual(fullFrameSize(192,192), {width:192,height:192});
  for(const values of [[0,0],[-1,720],[Infinity,720],[NaN,720]])assert.throws(()=>fullFrameSize(...values),/Camera/);
});

test('attendance image encoder reads every source pixel rather than the enrollment crop', async () => {
  const original=globalThis.document, calls=[];
  const blob=new Blob(['jpeg'],{type:'image/jpeg'});
  const canvas={getContext:()=>({drawImage:(...args)=>calls.push(args)}),toBlob:callback=>callback(blob)};
  globalThis.document={createElement:()=>canvas};
  try {
    const video={videoWidth:1920,videoHeight:1080};
    assert.equal(await fullFramePhoto(video),blob);
    assert.deepEqual(calls,[[video,0,0,1920,1080,0,0,1280,720]]);
    assert.equal(canvas.width,1280);assert.equal(canvas.height,720);
  } finally {globalThis.document=original;}
});
