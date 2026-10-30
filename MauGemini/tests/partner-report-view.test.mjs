import test from 'node:test';
import assert from 'node:assert/strict';
import { changedReportFields, localDateTimeInput, reportRows } from '../src/partnerReportView.ts';

test('missing out stays separate from pending admissions and complete pairs',()=>{
  const rows=[{worker_id:'1',admitted:true,status:'complete'},{worker_id:'2',admitted:true,status:'missing_out'},{worker_id:'3',admitted:false,status:'pending_name'},{worker_id:'4',admitted:false,status:'cancelled'}];
  assert.deepEqual(reportRows(rows,'incomplete').map(row=>row.worker_id),['2']);
  assert.deepEqual(reportRows(rows,'pending').map(row=>row.worker_id),['3','4']);
  assert.equal(reportRows(rows,'all').length,4);
});
test('night shift wall time follows the batch timezone across midnight',()=>{
  assert.equal(localDateTimeInput('2026-10-30T17:30:05Z','Asia/Ho_Chi_Minh'),'2026-10-31T00:30:05');
  assert.equal(localDateTimeInput('2026-10-30T17:30:05Z','UTC'),'2026-10-30T17:30:05');
  assert.equal(localDateTimeInput(null,'Asia/Ho_Chi_Minh'),'');
});
test('changing a name never silently relabels original camera times as manual',()=>{
  const original={name:'Nguyễn A',in_at:'2026-10-30T01:00:00.123Z',out_at:null};
  const fields={name:'Nguyễn B',in_local:'2026-10-30T08:00:00',out_local:''};
  assert.deepEqual(changedReportFields(original,fields,'Asia/Ho_Chi_Minh'),{name:'Nguyễn B'});
  assert.deepEqual(changedReportFields(original,{...fields,name:original.name,in_local:''},'Asia/Ho_Chi_Minh'),{in_local:null});
  assert.deepEqual(changedReportFields(original,{...fields,name:original.name,out_local:'2026-10-30T17:00:00'},'Asia/Ho_Chi_Minh'),{out_local:'2026-10-30T17:00:00'});
});
