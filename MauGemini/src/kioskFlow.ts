export type Receipt = {status: 'recorded' | 'duplicate'; request_id: string; event_id: string; employee_code: string; employee_name: string; server_time: string; direction: 'in' | 'out'};
export type FlowState = {phase: 'aligning' | 'processing' | 'waiting' | 'committing' | 'recovering' | 'success' | 'retry' | 'offline' | 'disabled' | 'unauthorized'; feedback: string; stableFrames?: number; receipt?: Receipt; faceBox?: number[] | null};
export class KioskError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}
type Ports = { request: (path: string, options?: RequestInit) => Promise<any>; photo: () => Promise<Blob>; enabled: () => boolean; load: () => string | null; save: (id: string | null) => void; uuid: () => string; now: () => number; update: (state: FlowState) => void };
const base = '/api/kiosk/recognition';

function validReceipt(value: any, id: string): value is Receipt {
  return value && ['recorded', 'duplicate'].includes(value.status) && value.request_id === id && typeof value.event_id === 'string' && value.event_id.length > 0 && typeof value.employee_code === 'string' && typeof value.employee_name === 'string' && ['in','out'].includes(value.direction) && Number.isFinite(Date.parse(value.server_time));
}

export class KioskFlow {
  private ports: Ports;
  private id: string | null;
  private busy = false;
  private stopped = false;
  private unauthorized = false;
  private waitUntil = 0;
  private awaitLeave = false;
  private image: {index: number; blob: Blob} | null = null;
  state: FlowState = {phase:'aligning',feedback:'Đứng trong tầm nhìn camera, nhìn thẳng và giữ yên.'};

  constructor(ports: Ports) { this.ports = ports; this.id = ports.load(); }
  stop() { this.stopped = true; this.image = null; }
  get hasPending() { return this.id !== null; }
  private emit(state: FlowState) { if (!this.stopped) { this.state = {...state,faceBox:state.faceBox === undefined && this.id ? this.state.faceBox : state.faceBox,stableFrames:state.stableFrames ?? (this.id ? this.state.stableFrames : 0)}; this.ports.update(this.state); } }
  private clear() { this.ports.save(null); this.id = null; this.image = null; }
  private done(value: unknown) {
    if (!this.id || !validReceipt(value, this.id)) throw new KioskError(503,'Chưa nhận được biên nhận hợp lệ. Đang kiểm tra lại kết quả.');
    this.clear(); this.awaitLeave = true; this.waitUntil = this.ports.now() + 4000;
    this.emit({phase:'success',feedback:value.status === 'recorded' ? 'Đã ghi nhận chấm công.' : value.direction === 'in' ? 'Đã quét vào ca. Không ghi thêm lượt.' : 'Đã quét ra ca. Không ghi thêm lượt.',receipt:value,stableFrames:3});
  }
  private async commit() {
    if (!this.id) return;
    this.emit({phase:'committing',feedback:'Đang lưu chấm công trên máy chủ…'});
    const receipt = await this.ports.request(`/api/kiosk/attendance/${this.id}/commit`,{method:'POST',headers:{'X-Kiosk-Intent':'record-attendance'},body:'{}'});
    if (!this.stopped) this.done(receipt);
  }

  async step() {
    if (this.busy || this.stopped || this.unauthorized || this.ports.now() < this.waitUntil) return;
    this.busy = true;
    try {
      if (this.id) {
        this.emit({phase:'recovering',feedback:'Đang kiểm tra trạng thái yêu cầu…'});
        let session;
        try { session = await this.ports.request(`${base}/sessions/${this.id}`); }
        catch (error) {
          if (!(error instanceof KioskError) || error.status !== 404) throw error;
          if (!this.ports.enabled()) { this.emit({phase:'disabled',feedback:'Chưa bật ghi công. Yêu cầu đang chờ được giữ để kiểm tra lại.'}); return; }
          session = await this.ports.request(base + '/sessions', {method:'POST',headers:{'X-Kiosk-Intent':'start-recognition'},body:JSON.stringify({request_id:this.id})});
        }
        if (this.stopped) return;
        if (session.request_id !== this.id) throw new KioskError(503,'Trạng thái không khớp yêu cầu. Đang kiểm tra lại.');
        if (session.state === 'used') { this.done(session.receipt); return; }
        if (session.state === 'rejected') { this.clear(); this.waitUntil = this.ports.now() + 2000; this.emit({phase:'retry',feedback:'Chưa hoàn tất chuỗi ảnh. Nhìn thẳng và thử lại.'}); return; }
        if (!this.ports.enabled()) { this.emit({phase:'disabled',feedback:'Ghi công đang tạm dừng. Kết quả yêu cầu được kiểm tra trước khi thử lại.'}); return; }
        if (session.state === 'verified') {
          if (session.needs_supervisor) { this.emit({phase:'waiting',feedback:'Chuỗi ảnh đã đạt. Chờ quản trị đối chiếu đúng người trước khi ghi công.',stableFrames:3}); this.waitUntil = this.ports.now()+800; return; }
          await this.commit();
          return;
        }
        if (session.state !== 'pending' || !Number.isInteger(session.next_frame_index) || session.next_frame_index < 1 || session.next_frame_index > 12 || typeof session.capture_nonce !== 'string') throw new KioskError(503,'Trạng thái nhận diện chưa hợp lệ. Đang kiểm tra lại.');
        const index = session.next_frame_index;
        if (!this.image || this.image.index !== index) this.image = {index,blob:await this.ports.photo()};
        if (this.stopped) return;
        this.emit({phase:'processing',feedback:'Đang nhận diện trên máy chủ local…'});
        const frame = await this.ports.request(`${base}/sessions/${this.id}/frames/${index}`, {method:'POST',headers:{'Content-Type':'image/jpeg','X-Kiosk-Intent':'capture-recognition','X-Capture-Nonce':session.capture_nonce},body:this.image.blob});
        if (this.stopped) return;
        this.image = null;
        this.emit({phase:frame.state === 'verified' ? 'waiting' : frame.state === 'rejected' ? 'retry' : 'aligning',feedback:frame.feedback || 'Nhìn thẳng và giữ yên.',stableFrames:frame.stable_frames || 0,faceBox:frame.face_box ?? null});
        // The final frame already reports the server's decision. Avoid waiting
        // another 500 ms poll when automatic commit is explicitly permitted.
        if (frame.state === 'verified' && frame.needs_supervisor === false && this.ports.enabled()) await this.commit();
        return;
      }
      const photo = await this.ports.photo();
      if (this.stopped) return;
      const preview = await this.ports.request(base + '/preview',{method:'POST',headers:{'Content-Type':'image/jpeg','X-Kiosk-Intent':'preview-recognition'},body:photo});
      if (this.stopped) return;
      if (!this.ports.enabled()) {
        this.emit({phase:'disabled',feedback:(preview.feedback || 'Đang dò khuôn mặt trong toàn cảnh.')+' Đang kiểm tra tự động, chưa ghi công.',faceBox:preview.face_box ?? null});
        return;
      }
      if (this.awaitLeave) {
        this.emit({phase:'aligning',feedback:'Đã hoàn tất. Bước ra khỏi khung để sẵn sàng cho người tiếp theo.',faceBox:preview.face_box ?? null});
        if (preview.face_present === false) this.awaitLeave = false;
        return;
      }
      this.emit({phase:'aligning',feedback:preview.feedback || 'Nhìn thẳng và giữ yên.',faceBox:preview.face_box ?? null});
      if (!preview.ready) return;
      const id = this.ports.uuid();
      this.ports.save(id); this.id = id; // Persist request identity before the first write request.
      this.emit({phase:'processing',feedback:'Đang mở phiên nhận diện…'});
      await this.ports.request(base + '/sessions',{method:'POST',headers:{'X-Kiosk-Intent':'start-recognition'},body:JSON.stringify({request_id:id})});
    } catch (error) {
      if (this.stopped) return;
      const status = error instanceof KioskError ? error.status : 0;
      if (status === 410) { this.clear(); this.emit({phase:'retry',feedback:'Phiên đã hết hạn, chưa ghi công. Nhìn thẳng để bắt đầu lại.'}); }
      else if (status === 401) { this.clear(); this.unauthorized = true; this.emit({phase:'unauthorized',feedback:'Quyền kiosk đã hết hạn hoặc thay đổi. Ghép lại thiết bị và kiểm tra bảng công nếu lượt trước chưa rõ kết quả, rồi bật lại camera.'}); }
      else this.emit({phase:status === 0 ? 'offline' : status === 503 && this.id ? 'recovering' : 'retry',feedback:status === 0 ? 'Chưa kết nối được máy chủ. Giữ yêu cầu để kiểm tra lại khi có mạng.' : error instanceof Error ? error.message : 'Chưa xác nhận được kết quả. Đang kiểm tra lại.'});
      this.waitUntil = this.ports.now() + (status === 429 ? 1500 : 1000);
    } finally { this.busy = false; }
  }
}
