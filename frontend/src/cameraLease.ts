// Only a random tab owner is broadcast; no media, names or kiosk credentials.
// Keep a second OnTime tab from retaining an exclusive Windows camera stream.
export function connectCameraOwner(release:()=>void, channel:BroadcastChannel|null=typeof BroadcastChannel==='undefined'?null:new BroadcastChannel('ontime-camera-owner')){
  const owner=crypto.randomUUID();
  const receive=(event:MessageEvent)=>{if(event.data?.type==='claim-camera'&&event.data.owner!==owner)release();};
  channel?.addEventListener('message',receive);
  return {
    claim:()=>{channel?.postMessage({type:'claim-camera',owner});},
    close:()=>{channel?.removeEventListener('message',receive);channel?.close();},
  };
}
