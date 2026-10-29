export type PadObservation = {quality_accepted:boolean; feedback?:string; reason?:string; server_time:string; stored:false; attendance_recorded:false; pad:null|{model_id:string;ensemble_live_score:number;pad_ms:number;decision:'not_evaluated';validated_for_attendance:false;models:{context_clipped:boolean}[]}};
type Ports = {photo:()=>Promise<Blob>;preview:(photo:Blob)=>Promise<PadObservation>;current:()=>boolean;pause:()=>Promise<void>;update:(count:number)=>void};

export async function runPadTrial(ports:Ports) {
  const readings:PadObservation[]=[];
  let model:string|null=null;
  const check=()=>{if(!ports.current())throw new DOMException('Phép thử đã dừng.','AbortError');};
  for(let index=0;index<5;index++) {
    check();const photo=await ports.photo();check();
    const result=await ports.preview(photo);check();
    if(result.stored!==false||result.attendance_recorded!==false||!Number.isFinite(Date.parse(result.server_time)))throw new Error('Phản hồi phép thử chưa hợp lệ.');
    if(result.quality_accepted) {
      const pad=result.pad;
      if(!pad||pad.decision!=='not_evaluated'||pad.validated_for_attendance!==false||!Number.isFinite(pad.ensemble_live_score)||pad.ensemble_live_score<0||pad.ensemble_live_score>1||!Number.isFinite(pad.pad_ms)||pad.pad_ms<0||!Array.isArray(pad.models)||typeof pad.model_id!=='string'||!pad.model_id||(model&&model!==pad.model_id))throw new Error('Kết quả model thay đổi hoặc chưa hợp lệ. Thử lại cả phiên.');
      model=pad.model_id;
    } else if(result.pad!==null)throw new Error('Ảnh không đạt không được có quyết định PAD.');
    readings.push(result);ports.update(readings.length);
    if(index<4){await ports.pause();check();}
  }
  const scores=readings.flatMap(row=>row.pad?[row.pad.ensemble_live_score]:[]);
  return {schema:'experimental-pad-trial-v1',sample_unit:'one_session_with_five_correlated_frames',model_id:model,
    captured_frames:5,quality_accepted_frames:scores.length,readings,
    live_score_mean:scores.length?scores.reduce((a,b)=>a+b,0)/scores.length:null,
    live_score_min:scores.length?Math.min(...scores):null,live_score_max:scores.length?Math.max(...scores):null,
    context_clipped_frames:readings.filter(row=>row.pad?.models.some(model=>model.context_clipped)).length,
    threshold:null,decision:'not_evaluated',validated_for_attendance:false,images_vectors_exported:false,automatic_identity_lookup:false};
}
