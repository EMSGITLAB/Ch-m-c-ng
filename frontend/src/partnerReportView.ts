export type ReportRow={worker_id:string;code:string;name:string|null;admitted:boolean;status:string;status_label:string;in_at:string|null;out_at:string|null;raw_in_at:string|null;raw_out_at:string|null;worked_seconds:number|null;elapsed_seconds:number|null;unpaid_break_seconds:number|null;outside_shift_seconds:number|null;adjustment_revision:number;adjustments:{revision:number;reason:string;admin_id:number;at:string;overrides:Record<string,string|null>}[];original_events:{id:string;direction:string;server_time:string}[]};
export function reportRows(rows:ReportRow[],filter:string){return filter==='all'?rows:rows.filter(row=>filter==='complete'?row.status==='complete':filter==='incomplete'?row.admitted&&row.status!=='complete':!row.admitted);}
export function localDateTimeInput(value:string|null,timezone:string){
  if(!value)return '';
  const parts=new Intl.DateTimeFormat('en',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value));
  const part=(key:string)=>parts.find(value=>value.type===key)!.value;
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}:${part('second')}`;
}
export function changedReportFields(original:{name:string|null;in_at:string|null;out_at:string|null},input:{name:string;in_local:string;out_local:string},timezone:string){
  const result:Record<string,string|null>={};
  if(input.name.trim()!==(original.name||''))result.name=input.name.trim();
  if(input.in_local!==localDateTimeInput(original.in_at,timezone))result.in_local=input.in_local||null;
  if(input.out_local!==localDateTimeInput(original.out_at,timezone))result.out_local=input.out_local||null;
  return result;
}
