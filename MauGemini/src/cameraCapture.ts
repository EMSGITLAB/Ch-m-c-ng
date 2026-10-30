export function centerCrop(width: number, height: number) {
  if (width <= 0 || height <= 0) throw new Error('Camera chưa có hình.');
  const ratio = 4 / 3;
  const cropWidth = Math.min(width, height * ratio);
  const cropHeight = cropWidth / ratio;
  return { x: (width - cropWidth) / 2, y: (height - cropHeight) / 2, width: cropWidth, height: cropHeight };
}

export async function cameraPhoto(video: HTMLVideoElement): Promise<Blob> {
  const crop = centerCrop(video.videoWidth, video.videoHeight);
  const canvas = document.createElement('canvas'); canvas.width = 960; canvas.height = 720;
  // Same 4:3 centre crop as object-fit:cover in the visible camera frame.
  canvas.getContext('2d')!.drawImage(video, crop.x, crop.y, crop.width, crop.height, 0, 0, 960, 720);
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Không chụp được ảnh.')), 'image/jpeg', .88));
}

export function fullFrameSize(width: number, height: number, maxEdge = 1280) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) throw new Error('Camera chưa có hình.');
  if (!Number.isFinite(maxEdge) || maxEdge < 640 || maxEdge > 1600) throw new Error('Độ phân giải camera chưa hợp lệ.');
  const scale = Math.min(1, maxEdge / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

// Attendance scans the entire camera scene. Enrollment keeps its separate 4:3 crop.
export async function fullFramePhoto(video: HTMLVideoElement, maxEdge = 1280): Promise<Blob> {
  const size = fullFrameSize(video.videoWidth, video.videoHeight, maxEdge);
  const canvas = document.createElement('canvas'); canvas.width = size.width; canvas.height = size.height;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Không đọc được hình camera.');
  context.drawImage(video, 0, 0, video.videoWidth, video.videoHeight, 0, 0, size.width, size.height);
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Không chụp được ảnh.')), 'image/jpeg', .88));
}
