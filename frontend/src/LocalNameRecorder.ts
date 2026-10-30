// MediaRecorder only: no browser SpeechRecognition or remote speech service.
import { SpeechEndDetector } from './speechEndDetector.ts';
export const recordingMime=(recorder:typeof MediaRecorder)=>['audio/webm;codecs=opus','audio/mp4','audio/webm','audio/ogg;codecs=opus'].find(value=>recorder.isTypeSupported(value));
export class LocalNameRecorder {
  private generation=0;
  private stream:MediaStream|null=null;
  private recorder:MediaRecorder|null=null;
  private reject:((reason:Error)=>void)|null=null;
  private timer:ReturnType<typeof setTimeout>|null=null;
  private monitorTimer:ReturnType<typeof setInterval>|null=null;
  private monitor:AudioContext|null=null;
  private stopMonitor(){
    if(this.monitorTimer)clearInterval(this.monitorTimer);this.monitorTimer=null;
    if(this.monitor){void this.monitor.close().catch(()=>{});this.monitor=null;}
  }
  cancel(){
    this.generation++;
    this.reject?.(new Error('Đã dừng micro.'));this.reject=null;
    if(this.timer)clearTimeout(this.timer);this.timer=null;
    this.stopMonitor();
    if(this.recorder&&this.recorder.state!=='inactive')this.recorder.stop();this.recorder=null;
    this.stream?.getTracks().forEach(track=>track.stop());this.stream=null;
  }
  finish(){if(this.recorder?.state==='recording')this.recorder.stop();}
  async record(onReady:()=>void):Promise<Blob>{
    this.cancel();const generation=this.generation;
    if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined')throw new Error('Thiết bị chưa hỗ trợ micro tại trang này; vui lòng nhập tay.');
    const mime=recordingMime(MediaRecorder);if(!mime)throw new Error('Định dạng micro chưa hỗ trợ; vui lòng nhập tay.');
    const Audio=globalThis.AudioContext||(globalThis as typeof globalThis&{webkitAudioContext?:typeof AudioContext}).webkitAudioContext;
    // Resume in the microphone button's user gesture, before permission awaits.
    if(Audio){try{this.monitor=new Audio();void this.monitor.resume().catch(()=>{});}catch{this.monitor=null;}}
    let stream:MediaStream;
    try{stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});}
    catch(error){if(generation===this.generation)this.stopMonitor();throw error;}
    if(generation!==this.generation){stream.getTracks().forEach(track=>track.stop());throw new Error('Phiên micro đã thay đổi.');}
    this.stream=stream;
    return new Promise<Blob>((resolve,reject)=>{
      this.reject=reject;
      let recorder:MediaRecorder;
      try{recorder=new MediaRecorder(stream,{mimeType:mime});}
      catch{this.cancel();reject(new Error('Chưa mở được bộ thu âm; vui lòng nhập tay.'));return;}
      this.recorder=recorder;const chunks:Blob[]=[];let bytes=0;
      const cleanup=()=>{if(this.timer)clearTimeout(this.timer);this.timer=null;this.stopMonitor();stream.getTracks().forEach(track=>track.stop());this.stream=null;this.recorder=null;this.reject=null;};
      recorder.ondataavailable=event=>{
        if(generation!==this.generation)return;
        bytes+=event.data.size;
        if(bytes>2_000_000){this.cancel();reject(new Error('Âm thanh quá lớn; vui lòng nhập tay.'));return;}
        if(event.data.size)chunks.push(event.data);
      };
      recorder.onerror=()=>{if(generation!==this.generation)return;cleanup();reject(new Error('Micro gặp lỗi; vui lòng nhập tay.'));};
      recorder.onstop=()=>{if(generation!==this.generation)return;cleanup();resolve(new Blob(chunks,{type:mime}));};
      try{
        recorder.start(250);this.timer=setTimeout(()=>this.finish(),8000);
        if(this.monitor){
          try{
            const analyser=this.monitor.createAnalyser();analyser.fftSize=2048;
            const source=this.monitor.createMediaStreamSource(stream);source.connect(analyser);
            const samples=new Float32Array(analyser.fftSize),gate=new SpeechEndDetector(performance.now());
            this.monitorTimer=setInterval(()=>{
              if(generation!==this.generation||this.monitor?.state!=='running')return;
              analyser.getFloatTimeDomainData(samples);
              let sum=0;for(const value of samples)sum+=value*value;
              if(gate.update(performance.now(),Math.sqrt(sum/samples.length)))this.finish();
            },80);
          }catch{this.stopMonitor(); /* Manual stop and the 8-second cap remain. */}
        }
        onReady();
      }
      catch{cleanup();reject(new Error('Không thu được âm thanh; vui lòng nhập tay.'));}
    });
  }
}
