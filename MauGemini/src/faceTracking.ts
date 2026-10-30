export function mirrorFaceBox(value: unknown) {
  if (!Array.isArray(value) || value.length !== 4 || !value.every(v => typeof v === 'number' && Number.isFinite(v))) return null;
  const [x,y,width,height] = value;
  if (x < 0 || y < 0 || width <= 0 || height <= 0 || x + width > 1.000001 || y + height > 1.000001) return null;
  return {left:`${Math.max(0,1-x-width)*100}%`,top:`${y*100}%`,width:`${width*100}%`,height:`${height*100}%`};
}


// Keep the entire video visible inside the reference layout, including letterboxing.
export function sceneLayout(width:number,height:number,aspect:number) {
  if(![width,height,aspect].every(Number.isFinite)||Math.min(width,height,aspect)<=0)return {};
  const w=Math.min(width,height*aspect),h=w/aspect;
  return {width:`${w}px`,height:`${h}px`,left:`${(width-w)/2}px`,top:`${(height-h)/2}px`,position:'absolute' as const};
}
