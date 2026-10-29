export function mirrorFaceBox(value: unknown) {
  if (!Array.isArray(value) || value.length !== 4 || !value.every(v => typeof v === 'number' && Number.isFinite(v))) return null;
  const [x,y,width,height] = value;
  if (x < 0 || y < 0 || width <= 0 || height <= 0 || x + width > 1.000001 || y + height > 1.000001) return null;
  return {left:`${Math.max(0,1-x-width)*100}%`,top:`${y*100}%`,width:`${width*100}%`,height:`${height*100}%`};
}
