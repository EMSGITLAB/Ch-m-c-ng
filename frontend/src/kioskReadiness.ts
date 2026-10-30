/** Recording requires both the server switch and this browser's kiosk permission. */
export function kioskReadiness(status: {recognition_ready:boolean;attendance_enabled:boolean}|null,
  device: {active:boolean;paired:boolean}|null) {
  if(!status)return {code:'offline',canRecord:false,title:'Chưa kết nối máy chủ',
    feedback:'Chưa xác nhận được máy chủ. Khung định vị trên camera chưa phải kết quả chấm công.'};
  if(!device?.paired||!device.active)return {code:'unpaired',canRecord:false,title:'Chưa ghép quyền chấm công',
    feedback:'Camera chỉ định vị khuôn mặt. Ghép điểm chấm công để máy chủ nhận diện và ghi giờ vào/ra.'};
  if(!status.recognition_ready)return {code:'loading',canRecord:false,title:'Bộ nhận diện chưa sẵn sàng',
    feedback:'Đã ghép thiết bị, đang chờ bộ nhận diện trên máy chủ. Chưa ghi chấm công.'};
  if(!status.attendance_enabled)return {code:'paused',canRecord:false,title:'Ghi công đang tạm dừng',
    feedback:'Camera chỉ kiểm tra khuôn mặt. Quản trị cần bật cấu hình ghi công trên máy chủ.'};
  return {code:'ready',canRecord:true,title:'Sẵn sàng nhận diện',feedback:'Nhìn thẳng và giữ yên để nhận diện, ghi công tự động.'};
}
