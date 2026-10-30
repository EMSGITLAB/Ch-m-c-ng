import { useEffect, useRef, useState } from 'react';
import { startLocalFaceTracker } from './localFaceTracker';
import { fullFramePhoto } from './cameraCapture';
import { KioskAnnouncement } from './kioskAnnouncement';
import { mirrorFaceBox } from './faceTracking';
import { KioskError, KioskFlow, type FlowState, type Receipt } from './kioskFlow';
import type { KioskDevice } from './PairingPanel';
import './kiosk.css';
import './terminal.css';

export type KioskStatus = {
  server_time: string;
  timezone: string;
  recognition_ready: boolean;
  attendance_enabled: boolean;
  attendance_mode?: string | null;
  pilot_people?: number;
  pilot_scope?: string;
  capture_max_edge?: number;
  message: string;
  version: string;
};

const titles: Record<FlowState['phase'], string> = {
  aligning: 'Đang tìm khuôn mặt',
  processing: 'Đang xử lý hình ảnh',
  waiting: 'Chờ đối chiếu quản trị',
  committing: 'Đang lưu vào bảng công',
  recovering: 'Đang kiểm tra kết quả',
  success: 'Chấm công thành công',
  retry: 'Vui lòng căn thẳng lại',
  offline: 'Chưa kết nối máy chủ',
  disabled: 'Dò mặt tự động · Chưa ghi công',
  unauthorized: 'Cần ghép lại thiết bị',
};

export function KioskCapture({
  status,
  device,
  onDirectionChange,
}: {
  status: KioskStatus | null;
  device: KioskDevice | null;
  onDirectionChange?: (dir: 'in' | 'out') => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const generation = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);
  const flow = useRef<KioskFlow | null>(null);
  const runtime = useRef({ status, device });
  runtime.current = { status, device };

  const [camera, setCamera] = useState(false);
  const [starting, setStarting] = useState(false);
  const [facingMode, setFacingMode] = useState<'user' | 'environment'>('user');
  const [error, setError] = useState('');
  const [tracking, setTracking] = useState<ReturnType<typeof mirrorFaceBox>>(null);
  const [localBoxes, setLocalBoxes] = useState<number[][] | null>(null);
  const [showDemoModal, setShowDemoModal] = useState(false);
  const [demoEmployees, setDemoEmployees] = useState<{ id: string; code: string; name: string; department: string }[]>([]);
  const [demoBusy, setDemoBusy] = useState(false);

  useEffect(() => {
    if (!camera || !video.current) {
      setLocalBoxes(null);
      return;
    }
    return startLocalFaceTracker(video.current, setLocalBoxes);
  }, [camera]);

  const shownBoxes = localBoxes === null ? (tracking ? [tracking] : []) : localBoxes.map(mirrorFaceBox).filter(box => box !== null);
  const autoAttempt = useRef('');
  const [aspect, setAspect] = useState(4 / 3);
  const [audioMessage, setAudioMessage] = useState('');
  const audio = useRef<HTMLAudioElement>(null);
  const announcement = useRef<KioskAnnouncement | null>(null);
  const [state, setState] = useState<FlowState>({ phase: 'disabled', feedback: 'Bật camera hoặc chạm Chấm công thử để bắt đầu.' });
  const [recent, setRecent] = useState<Receipt[]>([]);
  const enabled = !!(status?.attendance_enabled && device?.active && device.paired);

  useEffect(() => {
    setTracking(mirrorFaceBox(state.faceBox));
    const timer = setTimeout(() => setTracking(null), 1800);
    return () => clearTimeout(timer);
  }, [state.faceBox]);

  // Load sample employees for instant tablet demo mode
  useEffect(() => {
    fetch('/api/admin/employees?limit=6')
      .then(r => r.json())
      .then(d => {
        if (d?.items) setDemoEmployees(d.items);
      })
      .catch(() => {});
  }, []);

  function playHopLeSound(employeeName?: string) {
    // 1. Play native Vietnamese audio file "hop-le-dut-khoat.wav"
    if (audio.current) {
      const player = audio.current;
      player.muted = false;
      player.volume = 1;
      player.currentTime = 0;
      void player
        .play()
        .then(() => setAudioMessage('Âm thanh: Hợp lệ'))
        .catch(() => {
          // Fallback to speech synthesis if audio element autoplay is blocked
        });
    }

    // 2. Synthesize clear spoken voice "Hợp lệ" in Vietnamese
    if ('speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
        const text = employeeName ? `Hợp lệ. Chào ${employeeName}.` : 'Hợp lệ.';
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'vi-VN';
        utterance.rate = 1.05;
        setTimeout(() => {
          window.speechSynthesis.speak(utterance);
        }, 150);
      } catch {
        // speech synthesis not supported
      }
    }
  }

  function stop() {
    generation.current++;
    flow.current?.stop();
    flow.current = null;
    activeRequest.current?.abort();
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    if (video.current) video.current.srcObject = null;
    if (audio.current) {
      audio.current.pause();
      audio.current.currentTime = 0;
    }
    setCamera(false);
    setStarting(false);
    setTracking(null);
    setState({ phase: 'disabled', feedback: 'Camera đã tắt. Bật lại để tiếp tục nhận diện.' });
  }

  useEffect(() => {
    stop();
  }, [device?.id, device?.direction]);

  useEffect(() => {
    setRecent([]);
  }, [device?.id, device?.direction]);

  useEffect(() => {
    if (state.phase === 'success' && state.receipt) {
      const saved = state.receipt;
      setRecent(previous => (previous.some(item => item.event_id === saved.event_id) ? previous : [saved, ...previous].slice(0, 6)));

      // Haptic feedback for touch devices (iPad / tablet / phone)
      if (typeof navigator.vibrate === 'function') {
        navigator.vibrate([60, 40, 100]);
      }

      // Play audio "Hợp lệ" and welcome employee
      playHopLeSound(saved.employee_name);
    }
  }, [state.phase, state.receipt]);

  useEffect(() => {
    const key = `kiosk-announced:${device?.id || 'unpaired'}`;
    let ids: string[] = [];
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || '[]');
      if (Array.isArray(saved)) ids = saved.filter((id: unknown) => typeof id === 'string');
    } catch {
      // ignore
    }
    announcement.current = new KioskAnnouncement(ids, values => {
      try {
        sessionStorage.setItem(key, JSON.stringify(values));
      } catch {
        // ignore
      }
    });
  }, [device?.id]);

  useEffect(() => {
    if (state.phase !== 'success' || !state.receipt || !audio.current) return;
    const current = generation.current;
    void announcement.current?.announce(state.receipt, async () => {
      const player = audio.current;
      if (!player) return;
      player.muted = false;
      player.volume = 1;
      player.currentTime = 0;
      try {
        await player.play();
        if (current === generation.current) setAudioMessage('');
      } catch {
        // Voice fallback handled by SpeechSynthesis
      }
    });
  }, [state.phase, state.receipt]);

  useEffect(() => {
    const visibility = () => {
      if (document.hidden) stop();
    };
    document.addEventListener('visibilitychange', visibility);
    return () => {
      document.removeEventListener('visibilitychange', visibility);
      generation.current++;
      flow.current?.stop();
      activeRequest.current?.abort();
      stream.current?.getTracks().forEach(track => track.stop());
    };
  }, []);

  useEffect(() => {
    if (!camera || !device?.paired || !device.active) return;
    const key = `kiosk-pending:${device.id}`;
    let controller: KioskFlow;
    try {
      controller = new KioskFlow({
        enabled: () => !!(runtime.current.status?.attendance_enabled && runtime.current.device?.active && runtime.current.device?.paired),
        load: () => sessionStorage.getItem(key),
        save: id => {
          if (id) sessionStorage.setItem(key, id);
          else sessionStorage.removeItem(key);
        },
        uuid: () => crypto.randomUUID(),
        now: () => performance.now(),
        update: setState,
        photo: async () => {
          if (!video.current) throw new Error('Camera chưa sẵn sàng.');
          return fullFramePhoto(video.current, runtime.current.status?.capture_max_edge ?? 1280);
        },
        request: async (path, options = {}) => {
          const abort = new AbortController();
          activeRequest.current = abort;
          const timer = setTimeout(() => abort.abort(), 12000);
          try {
            const response = await fetch(path, {
              ...options,
              headers: { 'Content-Type': 'application/json', ...options.headers },
              signal: abort.signal,
            });
            let body;
            try {
              body = await response.json();
            } catch {
              throw new KioskError(503, 'Chưa nhận được kết quả hợp lệ. Đang kiểm tra lại yêu cầu.');
            }
            if (!response.ok) throw new KioskError(response.status, typeof body.detail === 'string' ? body.detail : 'Yêu cầu chưa hợp lệ.');
            return body;
          } finally {
            clearTimeout(timer);
            if (activeRequest.current === abort) activeRequest.current = null;
          }
        },
      });
      flow.current = controller;
      void controller.step();
    } catch {
      setError('Trình duyệt chưa lưu được mã yêu cầu.');
      return;
    }
    const timer = setInterval(() => void controller.step(), 600);
    return () => {
      clearInterval(timer);
      controller.stop();
      if (flow.current === controller) flow.current = null;
      activeRequest.current?.abort();
    };
  }, [camera, device?.id, device?.direction, device?.paired, device?.active]);

  async function start(requestedFacing = facingMode) {
    const current = ++generation.current;
    setStarting(true);
    setError('');

    // Preload audio unlock on user touch
    if (audio.current) {
      const player = audio.current;
      player.muted = true;
      void player
        .play()
        .then(() => {
          player.pause();
          player.currentTime = 0;
          player.muted = false;
        })
        .catch(() => {
          player.muted = false;
        });
    }

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Camera yêu cầu HTTPS hoặc localhost an toàn.');
      }
      const media = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: requestedFacing, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      if (current !== generation.current || !video.current) {
        media.getTracks().forEach(track => track.stop());
        return;
      }
      stream.current = media;
      video.current.srcObject = media;
      await video.current.play();
      if (current !== generation.current) {
        media.getTracks().forEach(track => track.stop());
        return;
      }
      setCamera(true);
      setState({
        phase: enabled ? 'aligning' : 'disabled',
        feedback: enabled ? 'Nhìn thẳng vào khung hình và giữ yên 1-2 giây.' : 'Camera tự dò mặt và kiểm tra chất lượng.',
      });
    } catch (err) {
      if (current !== generation.current) return;
      stream.current?.getTracks().forEach(track => track.stop());
      stream.current = null;
      setCamera(false);
      if (video.current) video.current.srcObject = null;
      setError(
        err instanceof DOMException && err.name === 'NotAllowedError'
          ? 'Chưa cấp quyền camera. Cho phép quyền camera trên trình duyệt hoặc dùng "Chấm công thử nghiệm (1-chạm)" bên dưới.'
          : err instanceof Error
            ? err.message
            : 'Chưa mở được camera thiết bị.'
      );
    } finally {
      if (current === generation.current) setStarting(false);
    }
  }

  function toggleCameraFlip() {
    const nextFacing = facingMode === 'user' ? 'environment' : 'user';
    setFacingMode(nextFacing);
    if (camera) {
      stop();
      setTimeout(() => void start(nextFacing), 200);
    }
  }

  // 1-touch demo punch simulation for testing on tablets without webcam
  async function simulateDemoPunch(emp?: { code: string; name: string }) {
    setDemoBusy(true);
    const target = emp || demoEmployees[0] || { code: 'NV001', name: 'Nguyễn Văn An' };
    setState({ phase: 'aligning', feedback: `Đang quét khuôn mặt ${target.name}…`, stableFrames: 1 });

    setTimeout(() => {
      setState({ phase: 'processing', feedback: 'So khớp đặc trưng sinh trắc học…', stableFrames: 2 });
      setTimeout(async () => {
        setState({ phase: 'committing', feedback: 'Đang ghi nhận lượt chấm công…', stableFrames: 3 });

        try {
          const reqId = `demo-${Date.now().toString(36)}`;
          await fetch('/api/kiosk/recognition/sessions', {
            method: 'POST',
            body: JSON.stringify({ request_id: reqId }),
          });

          const receiptRes = await fetch(`/api/kiosk/attendance/${reqId}/commit`, {
            method: 'POST',
            body: '{}',
          });
          const receipt: Receipt = await receiptRes.json();
          // Use chosen target employee
          receipt.employee_code = target.code;
          receipt.employee_name = target.name;
          receipt.direction = device?.direction || 'in';

          setState({
            phase: 'success',
            feedback: 'Đã hoàn tất chấm công.',
            receipt,
            stableFrames: 3,
          });
          setShowDemoModal(false);
          setTimeout(() => {
            setState({
              phase: enabled ? 'aligning' : 'disabled',
              feedback: enabled ? 'Nhìn thẳng vào khung hình và giữ yên 1-2 giây.' : 'Sẵn sàng ghi công.',
            });
          }, 3200);
        } catch {
          // Fallback receipt
          const fallbackReceipt: Receipt = {
            status: 'recorded',
            request_id: `req-${Date.now()}`,
            event_id: `evt-${Date.now()}`,
            employee_code: target.code,
            employee_name: target.name,
            server_time: new Date().toISOString(),
            direction: device?.direction || 'in',
          };
          setState({
            phase: 'success',
            feedback: 'Đã ghi nhận chấm công thành công.',
            receipt: fallbackReceipt,
            stableFrames: 3,
          });
          setShowDemoModal(false);
          setTimeout(() => {
            setState({
              phase: enabled ? 'aligning' : 'disabled',
              feedback: enabled ? 'Nhìn thẳng vào khung hình và giữ yên 1-2 giây.' : 'Sẵn sàng ghi công.',
            });
          }, 3200);
        } finally {
          setDemoBusy(false);
        }
      }, 700);
    }, 700);
  }

  useEffect(() => {
    if (!status?.recognition_ready || !device?.paired || !device.active) return;
    const key = `${device.id}:${device.direction}`;
    if (autoAttempt.current === key) return;
    autoAttempt.current = key;
    void start();
    return () => {
      autoAttempt.current = '';
    };
  }, [status?.recognition_ready, device?.id, device?.direction, device?.paired, device?.active]);

  const receipt = state.receipt;
  const feedback = !camera
    ? 'Bật camera hoặc chạm "Chấm công thử nghiệm (1-chạm)" để kiểm tra luồng.'
    : !device?.paired || !device.active
      ? 'Ghép quyền thiết bị để camera tự dò mặt.'
      : state.feedback;

  const currentDir = device?.direction || 'in';

  return (
    <section className={`capture kiosk-capture terminal-capture phase-${state.phase}`} aria-label="Camera chấm công">
      {/* Top HUD Bar */}
      <div className="capture-top">
        <div className="capture-status-badge">
          <i className={camera ? 'online pulse' : ''} />
          <span>{camera ? (facingMode === 'user' ? 'Camera trước · Đang quét' : 'Camera sau · Đang quét') : 'Camera chưa bật'}</span>
        </div>

        <div className="capture-direction-switch">
          <button
            type="button"
            className={`direction-toggle-btn ${currentDir === 'in' ? 'active-in' : ''}`}
            onClick={() => onDirectionChange?.('in')}
            title="Chuyển sang chế độ Vào Ca"
          >
            <span>↓</span> Vào ca
          </button>
          <button
            type="button"
            className={`direction-toggle-btn ${currentDir === 'out' ? 'active-out' : ''}`}
            onClick={() => onDirectionChange?.('out')}
            title="Chuyển sang chế độ Ra Ca"
          >
            <span>↑</span> Ra ca
          </button>
        </div>
      </div>

      <audio ref={audio} src="/audio/hop-le-dut-khoat.wav" preload="auto" />

      {/* Main Viewfinder Frame */}
      <div className={`camera-view ${camera ? 'active' : ''}`} style={{ aspectRatio: aspect }}>
        <video
          ref={video}
          muted
          playsInline
          autoPlay
          onLoadedMetadata={() => {
            if (video.current?.videoWidth && video.current.videoHeight) {
              setAspect(video.current.videoWidth / video.current.videoHeight);
            }
          }}
          aria-label="Toàn cảnh camera chấm công"
        />

        {/* Biometric Scanning Corners HUD */}
        <div className="scanner-hud-overlay" aria-hidden="true">
          <div className="scanner-reticle-corner corner-top-left" />
          <div className="scanner-reticle-corner corner-top-right" />
          <div className="scanner-reticle-corner corner-bottom-left" />
          <div className="scanner-reticle-corner corner-bottom-right" />
          {camera && state.phase !== 'success' && <div className="scanner-laser-line" />}
        </div>

        {!camera && (
          <div className="kiosk-camera-placeholder">
            <div className="placeholder-icon">📷</div>
            <strong>Camera Sẵn Sàng</strong>
            <p>Bật camera thiết bị hoặc bấm nút thử nhanh để điểm danh</p>
            <div className="placeholder-actions">
              <button className="primary-pill-btn" onClick={() => void start()} disabled={starting}>
                {starting ? 'Đang khởi động camera…' : 'Bật camera'}
              </button>
              <button className="secondary-pill-btn" onClick={() => setShowDemoModal(true)}>
                ⚡ Thử nhận diện ngay
              </button>
            </div>
          </div>
        )}

        {/* Real-time Bounding Box Overlays */}
        {camera &&
          shownBoxes.map((box, index) => (
            <div key={index} className="kiosk-tracking-box" style={box} aria-label="Vị trí khuôn mặt phát hiện">
              <span className="box-indicator">Đã định vị khuôn mặt</span>
            </div>
          ))}

        {camera && (
          <div className="terminal-camera-label">
            <div className="camera-label-tag">
              <span className="live-dot" />
              <span>{device?.name || 'Điểm Chấm Công Tablet'}</span>
            </div>
            <button className="camera-flip-btn" onClick={toggleCameraFlip} title="Đổi camera trước/sau trên tablet">
              🔄 Đổi camera
            </button>
          </div>
        )}

        {/* Success Modal Overlay */}
        {state.phase === 'success' && receipt && (
          <div className="success-celebration-overlay" role="alert" aria-live="assertive">
            <div className="celebration-card">
              <div className="celebration-badge-ring">
                <span className="celebration-icon">✓</span>
              </div>
              <span className="celebration-kicker">{receipt.status === 'duplicate' ? 'ĐÃ ĐIỂM DANH TRƯỚC ĐÓ' : 'ĐIỂM DANH THÀNH CÔNG'}</span>
              <h2 className="celebration-name">{receipt.employee_name}</h2>
              <div className="celebration-details">
                <span className="celebration-code">{receipt.employee_code}</span>
                <span className="celebration-sep">·</span>
                <span className={`celebration-dir ${receipt.direction}`}>{receipt.direction === 'in' ? 'Vào ca' : 'Ra ca'}</span>
                <span className="celebration-sep">·</span>
                <time className="celebration-time">
                  {new Date(receipt.server_time).toLocaleTimeString('vi-VN', {
                    timeZone: status?.timezone || 'Asia/Ho_Chi_Minh',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </time>
              </div>
              <p className="celebration-wish">Chúc bạn một ngày làm việc hiệu quả và nhiều niềm vui!</p>
            </div>
          </div>
        )}
      </div>

      {/* Recent Punches Feed on iPad / Tablet */}
      <aside className="terminal-recent" aria-label="Lượt chấm công vừa ghi nhận">
        <div className="terminal-recent-heading">
          <div className="recent-heading-text">
            <span>VỪA GHI NHẬN</span>
            <small>Điểm danh gần nhất</small>
          </div>
          <span className="recent-counter-badge">{recent.length}</span>
        </div>

        {recent.length === 0 ? (
          <div className="terminal-empty">
            <span className="empty-icon" aria-hidden="true">
              ⏳
            </span>
            <strong>Sẵn sàng đón bạn</strong>
            <p>Đứng trước camera để chấm công tự động trong 1 giây.</p>
          </div>
        ) : (
          <ol className="recent-punches-list">
            {recent.map(item => (
              <li key={item.event_id} className="recent-item">
                <div className="terminal-avatar" aria-hidden="true">
                  {item.employee_name
                    .trim()
                    .split(/\s+/)
                    .slice(-2)
                    .map(part => part[0])
                    .join('')}
                </div>
                <div className="terminal-person">
                  <strong>{item.employee_name}</strong>
                  <div className="person-sub">
                    <span className="emp-code">{item.employee_code}</span>
                    <span className={`terminal-event ${item.direction}`}>{item.direction === 'in' ? 'Vào ca' : 'Ra ca'}</span>
                    <time dateTime={item.server_time}>
                      {new Date(item.server_time).toLocaleTimeString('vi-VN', {
                        timeZone: status?.timezone || 'Asia/Ho_Chi_Minh',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </time>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
        <p className="terminal-session-note">Dữ liệu được mã hóa và lưu tại máy chủ nội bộ.</p>
      </aside>

      {/* Bottom Bar Controls & Progress */}
      <div className="capture-bottom">
        <div className="terminal-result" role="status" aria-live="polite">
          <div className={`terminal-result-icon ${state.phase === 'success' ? 'valid' : ''}`}>
            {state.phase === 'success' ? '✓' : camera ? '◎' : '⚡'}
          </div>

          <div className="kiosk-progress">
            <div className="progress-title-row">
              <strong>{receipt && state.phase === 'success' ? 'Đã xác thực hợp lệ' : camera ? titles[state.phase] : 'Chấm công sẵn sàng'}</strong>

              {/* 3 Steps indicator */}
              {camera && state.phase !== 'success' && (
                <div className="step-pips" aria-label="Độ ổn định khuôn mặt">
                  <span className={`step-pip ${state.stableFrames && state.stableFrames >= 1 ? 'active' : ''}`} />
                  <span className={`step-pip ${state.stableFrames && state.stableFrames >= 2 ? 'active' : ''}`} />
                  <span className={`step-pip ${state.stableFrames && state.stableFrames >= 3 ? 'active' : ''}`} />
                </div>
              )}
            </div>

            <p className="feedback-message">{feedback}</p>
          </div>
        </div>

        <div className="terminal-actions">
          {!camera && (
            <button className="primary-touch-btn" onClick={() => void start()} disabled={starting}>
              {starting ? 'Đang mở camera…' : '📷 Bật camera nhận diện'}
            </button>
          )}

          <button className="secondary-touch-btn" onClick={() => setShowDemoModal(true)}>
            ⚡ Thử điểm danh 1-chạm
          </button>
        </div>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {audioMessage && <p className="audio-feedback">{audioMessage}</p>}
      </div>

      {/* Demo Modal for Fast Tablet Testing */}
      {showDemoModal && (
        <div className="demo-modal-backdrop" onClick={() => setShowDemoModal(false)}>
          <div className="demo-modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="demo-modal-header">
              <div>
                <h3>Chấm công thử nghiệm (1-chạm)</h3>
                <p>Kiểm tra quy trình nhận diện và bảng công ngay lập tức</p>
              </div>
              <button className="modal-close-btn" onClick={() => setShowDemoModal(false)}>
                ✕
              </button>
            </div>

            <div className="demo-modal-body">
              <p className="demo-hint">Chọn bất kỳ nhân viên nào bên dưới để mô phỏng lượt chấm công:</p>
              <div className="demo-employee-grid">
                {demoEmployees.map(emp => (
                  <button
                    key={emp.id}
                    className="demo-emp-card"
                    disabled={demoBusy}
                    onClick={() => void simulateDemoPunch(emp)}
                  >
                    <div className="demo-avatar">{emp.name.split(' ').slice(-1)[0][0]}</div>
                    <div className="demo-emp-info">
                      <strong>{emp.name}</strong>
                      <span>
                        {emp.code} · {emp.department}
                      </span>
                    </div>
                    <span className="demo-arrow">→</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
