import { KioskError } from './kioskFlow.ts';
export type PartnerWorker={id:string;code:string;name:string|null;name_source?:string|null;state:string;name_revision:number;name_confirmed:boolean;admission_approved:boolean;pending_expires_at:string;in_at:string|null;out_at:string|null};
export type PartnerReceipt={status:'recorded'|'duplicate';request_id:string;event_id:string;worker_id:string;worker_code:string;worker_name:string;direction:'in'|'out';server_time:string;batch_id:string};
export type PartnerState={phase:'scanning'|'name'|'verifying'|'expired'|'other'|'success'|'error';feedback:string;worker?:PartnerWorker;receipt?:PartnerReceipt;faceBox?:number[]|null};
type Capture={request_id:string;state:string;next_frame_index:number;capture_nonce:string;worker?:PartnerWorker;owned_enrollment?:boolean;receipt?:PartnerReceipt;feedback?:string;face_box?:number[]|null};
type Ports={request:(path:string,options?:RequestInit)=>Promise<any>;photo:()=>Promise<Blob>;load:()=>string|null;save:(id:string|null)=>void;loadWorker?:()=>string|null;saveWorker?:(id:string|null)=>void;uuid:()=>string;now:()=>number;update:(state:PartnerState)=>void};
type NameCommand={workerId:string;name:string;source:'manual'|'voice'|'voice_edited';revision:number;resolve:()=>void;reject:(e:Error)=>void};
const base='/api/kiosk/partners';

// One request identity is persisted before writes, including across reloads.
export class PartnerFlow {
  state:PartnerState={phase:'scanning',feedback:'Nhìn thẳng và giữ yên để nhận diện tự động.'};
  private id:string|null;
  private capture:Capture|null=null;
  private busy=false;
  private stopped=false;
  private leaving=false;
  private nextAt=0;
  private command:NameCommand|null=null;
  private cancelling=false;
  private heldWorkerId:string|null;
  private ports:Ports;
  constructor(ports:Ports){this.ports=ports;this.id=ports.load();this.heldWorkerId=ports.loadWorker?.()||null;}
  stop(){this.stopped=true;this.command?.reject(new Error('Phiên camera đã dừng.'));this.command=null;}
  private emit(value:PartnerState){if(!this.stopped){this.state=value;this.ports.update(value);}}
  private clear(){this.ports.save(null);this.id=null;this.capture=null;}
  private hold(worker:PartnerWorker){this.heldWorkerId=worker.id;this.ports.saveWorker?.(worker.id);}
  private clearWorker(){this.heldWorkerId=null;this.ports.saveWorker?.(null);}
  private start(){return this.ports.request(base+'/captures',{method:'POST',headers:{'X-Kiosk-Intent':'start-partner-capture'},body:JSON.stringify({request_id:this.id,...(this.heldWorkerId?{expected_worker_id:this.heldWorkerId}:{})})});}
  confirmName(workerId:string,name:string,source:NameCommand['source'],revision:number){
    if(this.stopped||this.command)return Promise.reject(new Error('Phiên đang xử lý; chưa gửi thêm yêu cầu.'));
    return new Promise<void>((resolve,reject)=>{this.command={workerId,name,source,revision,resolve,reject};this.nextAt=0;void this.step();});
  }
  cancel(){this.cancelling=true;this.nextAt=0;void this.step();}
  private accept(capture:Capture){
    if(capture.request_id!==this.id)throw new Error('Mã phiên phản hồi chưa khớp.');
    this.capture=capture;
  }
  private success(receipt:PartnerReceipt){
    if(receipt.request_id!==this.id||!['recorded','duplicate'].includes(receipt.status)||!receipt.event_id||!receipt.worker_code||!receipt.worker_name||!Number.isFinite(Date.parse(receipt.server_time)))throw new Error('Biên nhận chưa hợp lệ; cần tra cứu lại.');
    this.command?.reject(new Error('Lượt quét đã hoàn tất.'));this.command=null;
    this.clear();this.clearWorker();this.leaving=true;
    this.emit({phase:'success',receipt,feedback:receipt.status==='duplicate'?(receipt.direction==='in'?'Đã quét vào ca':'Đã quét ra ca'):'Hợp lệ'});
  }
  async step(){
    if(this.busy||this.stopped||this.ports.now()<this.nextAt)return;
    this.busy=true;
    try{
      if(this.cancelling&&this.heldWorkerId){
        try{await this.ports.request(`${base}/workers/${this.heldWorkerId}/cancel`,{method:'POST',headers:{'X-Kiosk-Intent':'cancel-partner-admission'},body:'{}'});}
        catch(error){this.cancelling=false;if(!(error instanceof KioskError)||![404,410].includes(error.status))throw error;}
        if(this.stopped)return;
        this.command?.reject(new Error('Đã hủy tiếp nhận.'));this.command=null;this.cancelling=false;
        const expired=this.state.worker?.state==='expired';
        this.clear();this.clearWorker();this.leaving=!expired;this.emit({phase:'other',feedback:expired?'Nhìn lại camera để bắt đầu phiên mới.':'Đã hủy tiếp nhận. Chưa ghi công. Bước ra để bắt đầu phiên mới.'});return;
      }
      // Name entry is a separate step: poll only the held person, never
      // preview another face or allocate another ID behind the dialog.
      if(this.heldWorkerId&&!this.id){
        const worker:PartnerWorker=await this.ports.request(`${base}/workers/${this.heldWorkerId}`);
        if(this.stopped)return;
        if(worker.id!==this.heldWorkerId)throw new Error('Người trong phiên chưa khớp.');
        if(worker.state==='expired'||worker.state==='cancelled'){
          this.command?.reject(new Error('Phiên nhập tên đã hết hạn.'));this.command=null;
          this.emit({phase:'expired',worker,feedback:'Phiên nhập tên đã hết hạn; chưa ghi Vào. Bấm Quét lại để bắt đầu rõ ràng.'});this.nextAt=this.ports.now()+1500;return;
        }
        if(worker.state!=='pending'){
          this.command?.reject(new Error('Người này đã được xử lý.'));this.command=null;this.clearWorker();this.leaving=true;
          this.emit({phase:'other',feedback:'Đã quét vào ca bằng mã '+worker.code+'. Bước ra để tiếp tục.'});return;
        }
        if(this.command&&(this.command.workerId!==worker.id||this.command.revision!==worker.name_revision)){
          const saved=worker.name_confirmed&&worker.name_revision===this.command.revision+1&&worker.name===this.command.name&&worker.name_source===this.command.source;
          if(saved)this.command.resolve();else this.command.reject(new Error('Họ tên đã thay đổi. Kiểm tra lại trước khi xác nhận.'));
          this.command=null;
        }
        if(!this.command&&!worker.name_confirmed){
          this.emit({phase:'name',worker,feedback:'Đã nhận diện khuôn mặt. Vui lòng đọc hoặc nhập họ tên.'});
          this.nextAt=this.ports.now()+1500;return;
        }
        this.emit({phase:'verifying',worker,feedback:'Nhìn lại camera để xác nhận đúng khuôn mặt đang khai tên.'});
        this.id=this.ports.uuid();this.ports.save(this.id);this.accept(await this.start());return;
      }
      if(!this.id){
        const preview=await this.ports.request(base+'/preview',{method:'POST',headers:{'Content-Type':'image/jpeg','X-Kiosk-Intent':'preview-partner-face'},body:await this.ports.photo()});
        if(this.stopped)return;
        if(this.leaving){if(preview.face_present===false){this.leaving=false;this.emit({phase:'scanning',feedback:'Sẵn sàng cho người tiếp theo.'});}return;}
        if(!preview.ready){this.emit({...this.state,feedback:preview.feedback,faceBox:preview.face_box});return;}
        this.id=this.ports.uuid();this.ports.save(this.id);
        this.accept(await this.start());
        return;
      }
      try{this.accept(await this.ports.request(`${base}/captures/${this.id}`));}
      catch(error){
        if(error instanceof KioskError&&error.status===404){
          this.accept(await this.start());
        }else throw error;
      }
      if(this.stopped)return;
      let current=this.capture!;
      if(current.state==='used'&&current.receipt){this.success(current.receipt);return;}
      if(current.state==='rejected'){
        this.clear();this.emit({...this.state,feedback:current.feedback||'Quét lại khuôn mặt hiện tại để tiếp tục.'});return;
      }
      if(current.state==='pending'){
        this.accept(await this.ports.request(`${base}/captures/${this.id}/frames/${current.next_frame_index}`,{method:'POST',headers:{'Content-Type':'image/jpeg','X-Kiosk-Intent':'capture-partner-face','X-Capture-Nonce':current.capture_nonce},body:await this.ports.photo()}));
        if(this.stopped)return;
        current=this.capture!;
        if(current.state==='pending'){this.emit({...this.state,feedback:current.feedback||'Đang đối chiếu khuôn mặt…',faceBox:current.face_box});return;}
        if(current.state==='rejected'){this.clear();this.emit({...this.state,phase:'error',feedback:current.feedback||'Chưa đủ điều kiện ghi công; vui lòng thử lại.'});return;}
      }
      if(current.state!=='verified'||!current.worker)return;
      const worker=current.worker;
      if(this.command&&(this.command.workerId!==worker.id||this.command.revision!==worker.name_revision)){
        this.command.reject(new Error('Người hoặc họ tên đã thay đổi. Kiểm tra lại trước khi xác nhận.'));this.command=null;
      }
      if(worker.state==='pending'){
        if(!current.owned_enrollment){this.clear();this.leaving=true;this.emit({phase:'other',feedback:'Người này đang được tiếp nhận tại điểm khác. Không cấp thêm mã.'});return;}
        this.hold(worker);
        if(this.command){
          const command=this.command;
          const named=await this.ports.request(`${base}/workers/${worker.id}/name`,{method:'PUT',headers:{'X-Kiosk-Intent':'confirm-partner-name'},body:JSON.stringify({name:command.name,source:command.source,expected_revision:command.revision,proof_id:this.id})});
          if(this.stopped)return;
          this.command=null;command.resolve();this.clear();
          this.emit({phase:'verifying',worker:named,feedback:'Đã xác nhận họ tên. Giữ mặt trước camera để tự động ghi Vào.'});return;
        }
        if(!worker.name_confirmed){
          this.emit({phase:'name',worker,feedback:'Vui lòng đọc hoặc nhập đầy đủ họ tên, kiểm tra và xác nhận.'});
          this.clear();this.nextAt=this.ports.now()+1500;return;
        }
      }
      const receipt=await this.ports.request(`${base}/captures/${this.id}/commit`,{method:'POST',headers:{'X-Kiosk-Intent':'record-partner-attendance'},body:'{}'});
      if(!this.stopped)this.success(receipt);
    }catch(error){
      if(this.stopped)return;
      const status=error instanceof KioskError?error.status:0;
      if(status===410){this.clear();this.command?.reject(new Error('Phiên tiếp nhận hết hạn.'));this.command=null;this.emit({phase:'error',feedback:'Phiên hết hạn. Chưa ghi thêm công; quét lại để tiếp tục.'});}
      else{
        if(status===409&&this.capture?.state==='verified')this.clear();
        if([401,403,422].includes(status)){this.command?.reject(error as Error);this.command=null;}
        this.emit({...this.state,feedback:error instanceof Error?error.message:'Chưa nhận được kết quả, đang tra cứu lại yêu cầu.'});
      }
      this.nextAt=this.ports.now()+1200;
    }finally{this.busy=false;}
  }
}
