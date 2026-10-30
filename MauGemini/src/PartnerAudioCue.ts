// Decode the user's existing local sound once; unlock audible Web Audio in
// a real button gesture rather than relying on muted HTML media autoplay.
export class PartnerAudioCue {
  private context:AudioContext|null=null;
  private buffer:Promise<AudioBuffer>|null=null;
  private closed=false;
  private player:HTMLAudioElement;
  constructor(player:HTMLAudioElement){this.player=player;}
  unlock(){
    if(this.closed)return;
    const Audio=globalThis.AudioContext||(globalThis as typeof globalThis&{webkitAudioContext?:typeof AudioContext}).webkitAudioContext;
    if(!Audio)return;
    try{
      if(!this.context)this.context=new Audio();
      const context=this.context;
      void context.resume().catch(()=>{});
      const prime=context.createBufferSource();prime.buffer=context.createBuffer(1,1,context.sampleRate);
      prime.connect(context.destination);prime.start();
      if(!this.buffer){
        this.buffer=fetch(this.player.currentSrc||this.player.src).then(response=>{
          if(!response.ok)throw new Error('Chưa tải được âm thanh Hợp lệ.');return response.arrayBuffer();
        }).then(bytes=>context.decodeAudioData(bytes));
        void this.buffer.catch(()=>{this.buffer=null;});
      }
    }catch{/* HTML audio remains available for browsers without Web Audio. */}
  }
  async play(){
    if(this.closed)return;
    const context=this.context;
    if(context&&this.buffer){
      try{
        let timer:ReturnType<typeof setTimeout>|undefined;
        try{await Promise.race([context.resume(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Cần bấm để bật âm thanh.')),1200);})]);}
        finally{if(timer)clearTimeout(timer);}
        const buffer=await this.buffer;if(this.closed)return;
        if(context.state!=='running')throw new Error('Âm thanh chưa được cho phép.');
        const source=context.createBufferSource();source.buffer=buffer;source.connect(context.destination);source.start();return;
      }catch{/* Try the existing audio element before reporting to the user. */}
    }
    if(this.closed)return;
    this.player.currentTime=0;this.player.volume=1;this.player.muted=false;await this.player.play();
  }
  close(){this.closed=true;if(this.context){void this.context.close().catch(()=>{});this.context=null;}this.buffer=null;}
}
