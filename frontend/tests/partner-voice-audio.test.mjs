import assert from 'node:assert/strict';
import test from 'node:test';
import { SpeechEndDetector } from '../src/speechEndDetector.ts';
import { PartnerAudioCue } from '../src/PartnerAudioCue.ts';

test('a spoken name ends after a quiet tail instead of the full eight seconds',()=>{
  const gate=new SpeechEndDetector(0);let stoppedAt=0;
  for(let now=0;now<=8000;now+=80){if(gate.update(now,now<=1600?.04:.002)){stoppedAt=now;break;}}
  assert.ok(stoppedAt>=2600&&stoppedAt<3000);
});
test('brief pauses do not truncate a name; continuous noise remains bounded',()=>{
  const gate=new SpeechEndDetector(0);
  for(let now=0;now<3200;now+=80){assert.equal(gate.update(now,now>=900&&now<1500?.002:.04),false);}
  const noisy=new SpeechEndDetector(0);
  for(let now=0;now<8000;now+=80)assert.equal(noisy.update(now,.04),false);
  assert.equal(noisy.update(8000,.04),true);
});
test('quiet names and single level spikes retain the full recording fallback',()=>{
  const quiet=new SpeechEndDetector(0),spike=new SpeechEndDetector(0);
  for(let now=0;now<8000;now+=80){assert.equal(quiet.update(now,.001),false);assert.equal(spike.update(now,now===800?.1:.001),false);}
  assert.equal(quiet.update(8000,.001),true);
});

async function audioEnvironment(run){
  const oldAudio=globalThis.AudioContext,oldFetch=globalThis.fetch;
  let resumed=0,played=0,html=0,fetches=0,closed=0;
  const decoded={kind:'user-supplied-cue'};
  class Context{
    state='suspended';sampleRate=48000;destination={};
    resume(){resumed++;this.state='running';return Promise.resolve();}
    createBuffer(){return {kind:'silent-unlock'};}
    createBufferSource(){return {buffer:null,connect(){},start(){if(this.buffer===decoded)played++;}};}
    decodeAudioData(){return Promise.resolve(decoded);}
    close(){closed++;this.state='closed';return Promise.resolve();}
  }
  const player={src:'/audio/hop-le-user-fast-135.wav',currentSrc:'',muted:true,volume:0,currentTime:3,play:async()=>{html++;}};
  globalThis.AudioContext=Context;
  globalThis.fetch=async url=>{assert.equal(url,player.src);fetches++;return {ok:true,arrayBuffer:async()=>new ArrayBuffer(8)};};
  try{await run({player,get resumed(){return resumed;},get played(){return played;},get html(){return html;},get fetches(){return fetches;},get closed(){return closed;}});}
  finally{if(oldAudio===undefined)delete globalThis.AudioContext;else globalThis.AudioContext=oldAudio;globalThis.fetch=oldFetch;}
}
test('the button gesture unlocks audible Web Audio and decodes the original local file once',async()=>{
  await audioEnvironment(async env=>{
    const cue=new PartnerAudioCue(env.player);cue.unlock();assert.equal(env.resumed,1);
    await cue.play();cue.unlock();await cue.play();
    assert.equal(env.played,2);assert.equal(env.fetches,1);assert.equal(env.html,0);cue.close();
  });
});
test('audio fallback reports browser playback failure and close prevents delayed speech',async()=>{
  await audioEnvironment(async env=>{
    const cue=new PartnerAudioCue(env.player);cue.unlock();cue.close();await cue.play();
    assert.equal(env.played,0);assert.equal(env.html,0);assert.equal(env.closed,1);
    delete globalThis.AudioContext;
    env.player.play=async()=>{throw new Error('NotAllowedError');};
    const fallback=new PartnerAudioCue(env.player);fallback.unlock();
    await assert.rejects(fallback.play(),/NotAllowedError/);
    assert.equal(env.player.muted,false);assert.equal(env.player.volume,1);fallback.close();
  });
});
test('a suspended browser audio context cannot silently hang the success announcement',async()=>{
  await audioEnvironment(async env=>{
    const Base=globalThis.AudioContext;
    globalThis.AudioContext=class extends Base{resume(){return new Promise(()=>{});}};
    env.player.play=async()=>{throw new Error('NotAllowedError');};
    const cue=new PartnerAudioCue(env.player);cue.unlock();
    await assert.rejects(cue.play(),/NotAllowedError/);cue.close();
  });
});
