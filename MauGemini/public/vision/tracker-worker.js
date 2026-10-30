/* Local visual boxes only. Identity and attendance remain server decisions. */
/* global Vision */
let detector;
self.onmessage = async ({ data }) => {
  if (data.type === 'init') {
    try {
      importScripts('/vision/vision_bundle.js');
      const files = await Vision.FilesetResolver.forVisionTasks('/vision/wasm');
      detector = await Vision.FaceDetector.createFromOptions(files, {
        baseOptions: { modelAssetPath: '/vision/blaze_face_short_range.tflite', delegate: 'CPU' },
        runningMode: 'VIDEO', minDetectionConfidence: 0.6,
      });
      self.postMessage({ type: 'ready' });
    } catch { self.postMessage({ type: 'error' }); }
    return;
  }
  if (data.type === 'frame') {
    try {
      const start = performance.now();
      const result = detector.detectForVideo(data.image, data.timestamp);
      const boxes = result.detections.flatMap(item => {
        const b = item.boundingBox;
        if (!b) return [];
        const x = Math.max(0, b.originX / data.image.width), y = Math.max(0, b.originY / data.image.height);
        const right = Math.min(1, (b.originX + b.width) / data.image.width);
        const bottom = Math.min(1, (b.originY + b.height) / data.image.height);
        return right > x && bottom > y ? [[x, y, right - x, bottom - y]] : [];
      });
      self.postMessage({ type: 'result', boxes, elapsed: performance.now() - start });
    } catch { self.postMessage({ type: 'error' }); }
    finally { data.image.close(); }
  }
};
