// Local level monitoring only; no speech recognition or network request here.
export class SpeechEndDetector {
  private voicedMs=0;
  private lastVoice=0;
  private previous:number|null=null;
  private start:number;
  constructor(start:number){this.start=start;}
  update(now:number,rms:number){
    const delta=Math.max(0,Math.min(160,now-(this.previous??now)));
    this.previous=now;
    if(rms>=.012){this.voicedMs+=delta;this.lastVoice=now;}
    const elapsed=now-this.start;
    // If levels are too low to establish speech, keep the full bounded
    // recording instead of clipping a quiet name as though it were silence.
    return elapsed>=8000 || (this.voicedMs>=240&&elapsed>=1500&&now-this.lastVoice>=1000);
  }
}
