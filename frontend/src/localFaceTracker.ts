/** One in-flight frame, no queue, 10 fps maximum. All assets and pixels stay local. */
export function startLocalFaceTracker(video: HTMLVideoElement, update: (boxes: number[][] | null) => void) {
  let worker: Worker;
  try { worker = new Worker('/vision/tracker-worker.js'); }
  catch { update(null); return () => {}; }
  let stopped = false, ready = false, busy = false, last = -Infinity, videoTime = -1, raf = 0;
  const startup = setTimeout(fail, 15000);
  let watchdog: ReturnType<typeof setTimeout> | undefined;
  function fail() { if (stopped) return; stop(); update(null); }
  function stop() {
    stopped = true; clearTimeout(startup); clearTimeout(watchdog); cancelAnimationFrame(raf); worker.terminate();
  }
  worker.onerror = fail;
  worker.onmessage = ({ data }) => {
    if (stopped) return;
    if (data.type === 'error') { fail(); return; }
    if (data.type === 'ready') { ready = true; clearTimeout(startup); }
    if (data.type === 'result') { busy = false; clearTimeout(watchdog); update(data.boxes); }
  };
  worker.postMessage({ type: 'init' });
  async function frame(now: number) {
    if (stopped) return;
    raf = requestAnimationFrame(frame);
    if (!ready || busy || video.readyState < 2 || now - last < 100 || video.currentTime === videoTime) return;
    busy = true; last = now; videoTime = video.currentTime;
    try {
      // Only visual tracking uses this smaller bitmap. The recognition frame stays full scene at 1280.
      const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
      const image = await createImageBitmap(video, { resizeWidth: Math.max(1, Math.round(video.videoWidth * scale)), resizeHeight: Math.max(1, Math.round(video.videoHeight * scale)) });
      if (stopped) { image.close(); return; }
      watchdog = setTimeout(fail, 3000);
      worker.postMessage({ type: 'frame', image, timestamp: now }, [image]);
    } catch { fail(); }
  }
  raf = requestAnimationFrame(frame);
  return stop;
}
