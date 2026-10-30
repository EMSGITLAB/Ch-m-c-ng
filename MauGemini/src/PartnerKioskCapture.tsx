import { useEffect, useRef, useState } from 'react';
import { fullFramePhoto } from './cameraCapture';
import { mirrorFaceBox, sceneLayout } from './faceTracking';
import { KioskAnnouncement } from './kioskAnnouncement';
import { KioskError } from './kioskFlow';
import { LocalNameRecorder } from './LocalNameRecorder';
import { startLocalFaceTracker } from './localFaceTracker';
import { PairingPanel, type KioskDevice } from './PairingPanel';
import { PartnerFlow, type PartnerReceipt, type PartnerState } from './partnerFlow';
import { PartnerNameDialog } from './PartnerNameDialog';
import { connectCameraOwner } from './cameraLease';
import { PartnerAudioCue } from './PartnerAudioCue';
import './kiosk.css';
import './terminal.css';
import './partner.css';

type Context = {
  partner: { name: string; code: string };
  batch: {
    id: string;
    name: string;
    site: string;
    state: string;
    starts_at: string;
    ends_at: string;
    timezone: string;
    rules: { functional_trial?: boolean };
  };
  direction: 'in' | 'out';
  recognition_ready: boolean;
  recording_enabled: boolean;
  message: string;
};

const phaseTitles: Record<PartnerState['phase'], string> = {
  scanning: 'Đang tìm & đối chiếu khuôn mặt',
  name: 'Cần xác nhận họ tên nhân sự mới',
  verifying: 'Đang xác thực lại khuôn mặt',
  expired: 'Phiên nhập tên đã hết hạn',
  other: 'Thông báo điều phối phiên',
  success: 'Đã xác thực hợp lệ',
  error: 'Cần kiểm tra lại',
};

export function PartnerKioskCapture({
  device,
  onDeviceChange,
  onDirectionChange,
  directionBusy = false,
}: {
  device: KioskDevice | null;
  onDeviceChange: (device: KioskDevice | null) => void;
  onDirectionChange: (direction: 'in' | 'out') => void;
  directionBusy?: boolean;
}) {
  const cameraView = useRef<HTMLDivElement>(null);
  const [context, setContext] = useState<Context | null>(null);
  const [error, setError] = useState('');
  const [camera, setCamera] = useState(false);
  const [starting, setStarting] = useState(false);
  const [options, setOptions] = useState(false);
  const [pairing, setPairing] = useState(false);
  const [facingMode, setFacingMode] = useState<'user' | 'environment'>('user');
  const [aspect, setAspect] = useState(4 / 3);
  const [scene, setScene] = useState<ReturnType<typeof sceneLayout>>({});
  const [boxes, setBoxes] = useState<number[][] | null>(null);
  const [state, setState] = useState<PartnerState>({
    phase: 'scanning',
    feedback: 'Bật camera để bắt đầu.',
  });
  const [recent, setRecent] = useState<PartnerReceipt[]>([]);
  const [name, setName] = useState('');
  const [source, setSource] = useState<'manual' | 'voice' | 'voice_edited'>('manual');
  const [nameBusy, setNameBusy] = useState(false);
  const [voice, setVoice] = useState<'idle' | 'starting' | 'recording' | 'processing'>('idle');
  const [voiceMessage, setVoiceMessage] = useState('');
  const [audioMessage, setAudioMessage] = useState('');

  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const generation = useRef(0);
  const requests = useRef(new Set<AbortController>());
  const flow = useRef<PartnerFlow | null>(null);
  const recorder = useRef(new LocalNameRecorder());
  const voiceGeneration = useRef(0);
  const announcement = useRef<KioskAnnouncement | null>(null);
  const auto = useRef('');
  const lastWorker = useRef('');
  const voiceAbort = useRef<AbortController | null>(null);
  const cameraOwner = useRef<ReturnType<typeof connectCameraOwner> | null>(null);
  const audioCue = useRef<PartnerAudioCue | null>(null);

  useEffect(() => {
    const element = cameraView.current;
    if (!element) return;
    const resize = () => {
      const r = element.getBoundingClientRect();
      setScene(sceneLayout(r.width, r.height, aspect));
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    return () => observer.disconnect();
  }, [aspect]);

  useEffect(() => {
    if (!audio.current) return;
    const cue = new PartnerAudioCue(audio.current);
    audioCue.current = cue;
    return () => {
      cue.close();
      if (audioCue.current === cue) audioCue.current = null;
    };
  }, []);

  async function request(path: string, reqOptions: RequestInit = {}) {
    const controller = new AbortController();
    requests.current.add(controller);
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(path, {
        ...reqOptions,
        headers: { 'Content-Type': 'application/json', ...reqOptions.headers },
        signal: controller.signal,
      });
      const body = await response.json();
      if (!response.ok)
        throw new KioskError(
          response.status,
          typeof body.detail === 'string' ? body.detail : 'Yêu cầu chưa hợp lệ.'
        );
      return body;
    } finally {
      clearTimeout(timeout);
      requests.current.delete(controller);
    }
  }

  function cancelVoice() {
    voiceGeneration.current++;
    recorder.current.cancel();
    voiceAbort.current?.abort();
    voiceAbort.current = null;
    setVoice('idle');
  }

  function unlockAudio() {
    audioCue.current?.unlock();
  }

  function stop() {
    generation.current++;
    flow.current?.stop();
    flow.current = null;
    requests.current.forEach(controller => controller.abort());
    requests.current.clear();
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    if (video.current) video.current.srcObject = null;
    cancelVoice();
    setCamera(false);
    setStarting(false);
    setBoxes(null);
    setNameBusy(false);
  }

  useEffect(() => {
    const owner = connectCameraOwner(stop);
    cameraOwner.current = owner;
    return () => {
      owner.close();
      cameraOwner.current = null;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let alive = true;
    async function refresh() {
      try {
        const response = await fetch('/api/kiosk/partners/context', { signal: controller.signal });
        const body = await response.json();
        if (!alive) return;
        if (!response.ok) {
          setContext(null);
          setError(typeof body.detail === 'string' ? body.detail : 'Chưa có cấu hình điểm đối tác.');
          return;
        }
        setContext(body);
        setError(body.recording_enabled ? '' : body.message);
      } catch {
        if (alive) {
          setContext(null);
          setError('Chưa kết nối máy chủ local.');
        }
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 7000);
    return () => {
      alive = false;
      controller.abort();
      clearInterval(timer);
    };
  }, [device?.id, device?.direction, device?.partner_batch_id]);

  useEffect(() => {
    stop();
    setState({ phase: 'scanning', feedback: 'Nhìn thẳng và giữ yên. Camera sẽ tự nhận diện.' });
  }, [device?.id, device?.direction, context?.batch.id]);

  useEffect(() => {
    setRecent([]);
  }, [device?.id, context?.batch.id]);

  useEffect(() => {
    const key = 'partner-announced:' + (device?.id || 'unpaired');
    let ids: string[] = [];
    try {
      const parsed = JSON.parse(sessionStorage.getItem(key) || '[]');
      if (Array.isArray(parsed)) ids = parsed.filter(value => typeof value === 'string');
    } catch {
      /* Keep an in-memory event guard. */
    }
    announcement.current = new KioskAnnouncement(ids, values => {
      try {
        sessionStorage.setItem(key, JSON.stringify(values));
      } catch {
        /* Recognition does not depend on audio history. */
      }
    });
  }, [device?.id]);

  useEffect(() => {
    const receipt = state.receipt;
    if (!receipt) return;
    if (state.phase === 'success') {
      setRecent(prev =>
        prev.some(item => item.event_id === receipt.event_id) ? prev : [receipt, ...prev].slice(0, 6)
      );
    }
    void announcement.current?.announce(
      { ...receipt, employee_code: receipt.worker_code, employee_name: receipt.worker_name },
      async () => {
        try {
          await audioCue.current?.play();
          setAudioMessage('');
        } catch {
          setAudioMessage(
            'Trình duyệt chưa phát được âm thanh. Bấm Bật âm thanh và kiểm tra âm lượng thiết bị.'
          );
        }
      }
    );
  }, [state.receipt, state.phase]);

  useEffect(() => {
    const key = state.worker?.id || '';
    if (key !== lastWorker.current) {
      lastWorker.current = key;
      cancelVoice();
      setName(state.worker?.name || '');
      setSource('manual');
      setVoiceMessage('');
    }
  }, [state.worker?.id]);

  useEffect(() => {
    if (!camera || !video.current || ['name', 'expired'].includes(state.phase)) return;
    return startLocalFaceTracker(video.current, setBoxes);
  }, [camera, state.phase]);

  useEffect(() => {
    if (!camera || !device?.id || !context?.recording_enabled) return;
    const key = 'partner-pending:' + device.id;
    try {
      const controller = new PartnerFlow({
        request,
        photo: async () => {
          if (!video.current) throw new Error('Camera chưa sẵn sàng.');
          return fullFramePhoto(video.current);
        },
        load: () => sessionStorage.getItem(key),
        save: id => {
          if (id) sessionStorage.setItem(key, id);
          else sessionStorage.removeItem(key);
        },
        loadWorker: () => sessionStorage.getItem(key + ':worker'),
        saveWorker: id => {
          if (id) sessionStorage.setItem(key + ':worker', id);
          else sessionStorage.removeItem(key + ':worker');
        },
        uuid: () => crypto.randomUUID(),
        now: () => performance.now(),
        update: setState,
      });
      flow.current = controller;
      void controller.step();
      const timer = setInterval(() => void controller.step(), 500);
      return () => {
        clearInterval(timer);
        controller.stop();
        if (flow.current === controller) flow.current = null;
      };
    } catch {
      setError('Cho phép lưu dữ liệu của trang để giữ mã yêu cầu, rồi bật lại camera.');
    }
  }, [camera, device?.id, device?.direction, context?.batch.id, context?.recording_enabled]);

  async function start(requestedFacing = facingMode) {
    stop();
    const current = generation.current;
    setStarting(true);
    setError('');
    unlockAudio();
    cameraOwner.current?.claim();
    try {
      if (!navigator.mediaDevices?.getUserMedia)
        throw new Error('Camera cần localhost hoặc HTTPS tin cậy.');
      await new Promise(resolve => setTimeout(resolve, 200));
      if (current !== generation.current) return;
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
      if (current === generation.current) setCamera(true);
      else media.getTracks().forEach(track => track.stop());
    } catch (e) {
      if (current === generation.current) {
        stop();
        setError(
          e instanceof DOMException && e.name === 'NotReadableError'
            ? 'Camera đang được tab hoặc ứng dụng khác sử dụng. Tắt camera ở cửa sổ cũ rồi bật lại tại đây.'
            : e instanceof Error
              ? e.message
              : 'Chưa mở được camera.'
        );
      }
    } finally {
      if (current === generation.current) setStarting(false);
    }
  }

  useEffect(() => {
    if (!context?.recording_enabled || !device?.paired) return;
    const key = `${device.id}:${device.direction}:${context.batch.id}`;
    if (auto.current === key) return;
    auto.current = key;
    void start();
  }, [context?.batch.id, context?.recording_enabled, device?.id, device?.paired, device?.direction]);

  useEffect(() => {
    if (context && !context.recording_enabled) {
      auto.current = '';
      stop();
    }
  }, [context?.recording_enabled]);

  useEffect(() => {
    const visibility = () => {
      if (document.hidden) stop();
    };
    document.addEventListener('visibilitychange', visibility);
    return () => {
      document.removeEventListener('visibilitychange', visibility);
      generation.current++;
      flow.current?.stop();
      requests.current.forEach(controller => controller.abort());
      stream.current?.getTracks().forEach(track => track.stop());
      voiceGeneration.current++;
      recorder.current.cancel();
      voiceAbort.current?.abort();
    };
  }, []);

  function toggleCameraFlip() {
    const next = facingMode === 'user' ? 'environment' : 'user';
    setFacingMode(next);
    if (camera) {
      stop();
      void start(next);
    }
  }

  async function readName() {
    const worker = state.worker;
    if (!worker || !camera) return;
    cancelVoice();
    const current = voiceGeneration.current;
    const revision = worker.name_revision;
    setVoice('starting');
    setVoiceMessage('');
    try {
      const blob = await recorder.current.record(() => {
        if (current === voiceGeneration.current) setVoice('recording');
      });
      if (current !== voiceGeneration.current) return;
      setVoice('processing');
      const controller = new AbortController();
      voiceAbort.current = controller;
      const timeout = setTimeout(() => controller.abort(), 40000);
      try {
        const response = await fetch(
          `/api/kiosk/partners/workers/${worker.id}/speech?expected_revision=${revision}`,
          {
            method: 'POST',
            body: blob,
            signal: controller.signal,
            headers: {
              'Content-Type': blob.type,
              'X-Kiosk-Intent': 'transcribe-partner-name',
            },
          }
        );
        const body = await response.json();
        if (current !== voiceGeneration.current) return;
        if (!response.ok)
          throw new Error(
            typeof body.detail === 'string'
              ? body.detail
              : 'Chưa nhận rõ họ tên; vui lòng nhập tay.'
          );
        if (body.worker_id !== worker.id || body.expected_revision !== revision)
          throw new Error('Phiên đọc đã thay đổi. Vui lòng nhập tay.');
        setName(body.draft);
        setSource('voice');
        setVoiceMessage('Kiểm tra dấu và chính tả; sửa nếu cần rồi xác nhận.');
      } finally {
        clearTimeout(timeout);
        if (voiceAbort.current === controller) voiceAbort.current = null;
      }
    } catch (e) {
      if (current === voiceGeneration.current)
        setVoiceMessage(
          e instanceof DOMException && e.name === 'NotAllowedError'
            ? 'Micro chưa được cấp quyền. Chọn “Nhập bằng tay” để tiếp tục.'
            : e instanceof Error
              ? e.message
              : 'Chưa nhận rõ họ tên; vui lòng nhập tay.'
        );
    } finally {
      if (current === voiceGeneration.current) setVoice('idle');
    }
  }

  async function confirm() {
    if (!state.worker || !flow.current || !name.trim()) return;
    unlockAudio();
    cancelVoice();
    setNameBusy(true);
    setVoiceMessage('');
    try {
      await flow.current.confirmName(state.worker.id, name.trim(), source, state.worker.name_revision);
    } catch (e) {
      setVoiceMessage(e instanceof Error ? e.message : 'Chưa xác nhận được họ tên.');
    } finally {
      setNameBusy(false);
    }
  }

  const shown = (boxes ?? (state.faceBox ? [state.faceBox] : []))
    .map(mirrorFaceBox)
    .filter(box => box !== null);
  const worker = state.worker;
  const receipt = state.receipt;
  const canStart = !!context?.recording_enabled && !!device?.paired;
  const currentDir = device?.direction || context?.direction || 'in';

  async function testSound() {
    unlockAudio();
    try {
      await audioCue.current?.play();
      setAudioMessage('');
    } catch {
      setAudioMessage(
        'Chưa phát được âm thanh. Kiểm tra âm lượng và quyền âm thanh của trình duyệt.'
      );
    }
  }

  return (
    <section
      className={`capture kiosk-capture terminal-capture partner-kiosk-capture phase-${state.phase}`}
      aria-label="Chấm công đối tác"
    >
      {/* Top HUD Bar */}
      <div className="capture-top">
        <div className="capture-status-badge">
          <i className={camera ? 'online pulse' : ''} />
          <span>
            {!device?.paired
              ? 'Chưa ghép quyền thiết bị'
              : !context
                ? 'Chưa gán đợt đối tác'
                : !context.recording_enabled
                  ? context.message || 'Ghi công đối tác đang tạm dừng'
                  : camera
                    ? `${context.partner.name} · Đang quét`
                    : 'Camera đối tác đang nghỉ'}
          </span>
        </div>

        <div className="capture-direction-switch" aria-label="Chiều chấm công">
          <button
            type="button"
            className={`direction-toggle-btn ${currentDir === 'in' ? 'active-in' : ''}`}
            disabled={!context || !device?.paired || directionBusy || device.direction === 'in'}
            onClick={() => {
              unlockAudio();
              stop();
              onDirectionChange('in');
            }}
            title="Chuyển sang chế độ Vào Ca"
          >
            <span>↓</span> Vào ca
          </button>
          <button
            type="button"
            className={`direction-toggle-btn ${currentDir === 'out' ? 'active-out' : ''}`}
            disabled={!context || !device?.paired || directionBusy || device.direction === 'out'}
            onClick={() => {
              unlockAudio();
              stop();
              onDirectionChange('out');
            }}
            title="Chuyển sang chế độ Ra Ca"
          >
            <span>↑</span> Ra ca
          </button>
        </div>

        <button
          className="kiosk-options-button"
          aria-expanded={options}
          aria-controls="partner-option-controls"
          onClick={() => setOptions(value => !value)}
        >
          ⚙ {options ? 'Đóng tùy chọn' : 'Tùy chọn'}
        </button>

        {options && (
          <div
            className="kiosk-option-controls"
            id="partner-option-controls"
            aria-label="Tùy chọn camera và thiết bị đối tác"
          >
            <button
              className="secondary-pill-btn"
              disabled={starting || (!camera && !canStart)}
              onClick={() => (camera ? stop() : void start())}
            >
              {starting ? 'Đang mở…' : camera ? 'Tắt camera' : 'Bật camera'}
            </button>
            <button className="secondary-pill-btn" disabled={!camera} onClick={toggleCameraFlip}>
              Đổi camera trước/sau
            </button>
            <button className="secondary-pill-btn" onClick={() => setPairing(true)}>
              Ghép thiết bị
            </button>
            <button className="secondary-pill-btn" onClick={() => void testSound()}>
              Thử giọng đọc
            </button>
          </div>
        )}
      </div>

      <audio ref={audio} preload="auto" src="/audio/hop-le-user-fast-135.wav" />

      {/* Main Viewfinder Frame */}
      <div
        ref={cameraView}
        className={`camera-view ${camera ? 'active' : ''}`}
        style={{ aspectRatio: aspect }}
      >
        <div className="camera-scene" style={scene}>
          <video
            ref={video}
            autoPlay
            playsInline
            muted
            onLoadedMetadata={() => {
              if (video.current?.videoWidth && video.current.videoHeight) {
                setAspect(video.current.videoWidth / video.current.videoHeight);
              }
            }}
            aria-label="Toàn cảnh camera chấm công đối tác"
          />

          {camera &&
            shown.map((box, index) => (
              <div
                key={index}
                className="kiosk-tracking-box"
                style={box}
                aria-label="Vị trí khuôn mặt đối tác phát hiện"
              >
                <span className="box-indicator">Đã định vị khuôn mặt</span>
              </div>
            ))}
        </div>

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
            <div className="placeholder-icon">🤝</div>
            <strong>
              {!device?.paired
                ? 'Chưa ghép quyền thiết bị'
                : context
                  ? `${context.partner.name} · ${context.batch.name}`
                  : 'Chưa gán đợt đối tác'}
            </strong>
            <p>
              {!device?.paired
                ? 'Ghép điểm chấm công bằng mã 8 chữ số từ Quản trị → Thiết bị để kích hoạt quầy đối tác.'
                : context
                  ? `${context.batch.site} · Bật camera để tự động nhận diện và ghi công nhân sự đối tác.`
                  : 'Gán thiết bị cho đợt tại Quản trị → Chấm công đối tác để mở ca làm việc.'}
            </p>
            <div className="placeholder-actions">
              {!device?.paired ? (
                <button className="primary-pill-btn" onClick={() => setPairing(true)}>
                  Ghép thiết bị
                </button>
              ) : (
                <button
                  className="primary-pill-btn"
                  disabled={starting || !canStart}
                  onClick={() => void start()}
                >
                  {starting ? 'Đang mở…' : 'Bật camera'}
                </button>
              )}
              {!context && device?.paired && (
                <a className="secondary-pill-btn partner-link-btn" href="#admin">
                  Mở Quản trị Đối tác
                </a>
              )}
            </div>
          </div>
        )}

        {camera && (
          <div className="terminal-camera-label">
            <div className="camera-label-tag">
              <span className="live-dot" />
              <span>{device?.name || 'Điểm Chấm Công Đối Tác'}</span>
            </div>
            {context && (
              <span className="partner-batch-hud-pill">
                🏢 {context.partner.code} · {context.batch.name}
              </span>
            )}
          </div>
        )}

        {/* Success Celebration Overlay */}
        {state.phase === 'success' && receipt && (
          <div className="success-celebration-overlay" role="alert" aria-live="assertive">
            <div className="celebration-card">
              <div className="celebration-badge-ring">
                <span className="celebration-icon">✓</span>
              </div>
              <span className="celebration-kicker">
                {receipt.status === 'duplicate'
                  ? receipt.direction === 'in'
                    ? 'ĐÃ QUÉT VÀO CA ĐỐI TÁC'
                    : 'ĐÃ QUÉT RA CA ĐỐI TÁC'
                  : 'ĐIỂM DANH ĐỐI TÁC HỢP LỆ'}
              </span>
              <h2 className="celebration-name">{receipt.worker_name}</h2>
              <div className="celebration-details">
                <span className="celebration-code">{receipt.worker_code}</span>
                <span className="celebration-sep">·</span>
                <span className={`celebration-dir ${receipt.direction}`}>
                  {receipt.direction === 'in' ? 'Vào ca' : 'Ra ca'}
                </span>
                <span className="celebration-sep">·</span>
                <time className="celebration-time">
                  {new Date(receipt.server_time).toLocaleTimeString('vi-VN', {
                    timeZone: context?.batch.timezone || 'Asia/Ho_Chi_Minh',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </time>
              </div>
              <p className="celebration-wish">
                {receipt.status === 'duplicate'
                  ? 'Giữ nguyên giờ đã ghi nhận. Không ghi thêm lượt.'
                  : 'Đã ghi nhận giờ công đối tác thành công!'}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Right Sidebar: Active Batch Info & Recent Partner Punches */}
      <aside className="terminal-recent partner-terminal-sidebar" aria-label="Thông tin đợt và lượt vừa ghi nhận">
        <div className="terminal-recent-heading">
          <div className="recent-heading-text">
            <span>ĐỢT ĐỐI TÁC</span>
            <small>{context ? context.partner.name : 'Chưa gán đợt'}</small>
          </div>
          <span className="recent-counter-badge">{recent.length}</span>
        </div>

        {context ? (
          <div className="partner-sidebar-batch-card">
            <div className="partner-sidebar-vendor">
              {context.partner.code} · {context.partner.name}
            </div>
            <strong className="partner-sidebar-batch-name">{context.batch.name}</strong>
            <div className="partner-sidebar-meta">
              <span>📍 Vị trí: {context.batch.site}</span>
              <span>
                🕒 Khung ca:{' '}
                {new Date(context.batch.starts_at).toLocaleTimeString('vi-VN', {
                  timeZone: context.batch.timezone,
                  hour: '2-digit',
                  minute: '2-digit',
                })}{' '}
                –{' '}
                {new Date(context.batch.ends_at).toLocaleTimeString('vi-VN', {
                  timeZone: context.batch.timezone,
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
          </div>
        ) : (
          <div className="terminal-empty">
            <span className="empty-icon" aria-hidden="true">
              🤝
            </span>
            <strong>Chưa gán đợt đối tác</strong>
            <p>Vào Quản trị → Chấm công đối tác để gán thiết bị này cho đợt làm việc.</p>
          </div>
        )}

        {worker && worker.state === 'pending' && (
          <div className="partner-worker-active-card">
            <div className="partner-worker-card-head">
              <span>Đang tiếp nhận</span>
              <span className="partner-worker-state-pill">Mã tạm</span>
            </div>
            <strong>{worker.code}</strong>
            <p>
              Hết phiên lúc{' '}
              {new Date(worker.pending_expires_at).toLocaleTimeString('vi-VN', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })}
            </p>
          </div>
        )}

        {recent.length === 0 ? (
          <div className="terminal-empty">
            <span className="empty-icon" aria-hidden="true">
              ⏳
            </span>
            <strong>Sẵn sàng tiếp nhận</strong>
            <p>Nhìn thẳng vào camera để tự động nhận diện hoặc khai báo tên nếu là người mới.</p>
          </div>
        ) : (
          <ol className="recent-punches-list">
            {recent.map(item => (
              <li key={item.event_id} className="recent-item">
                <div className="terminal-avatar" aria-hidden="true">
                  {item.worker_name
                    .trim()
                    .split(/\s+/)
                    .slice(-2)
                    .map(part => part[0])
                    .join('')}
                </div>
                <div className="terminal-person">
                  <strong>{item.worker_name}</strong>
                  <div className="person-sub">
                    <span className="emp-code">{item.worker_code}</span>
                    <span className={`terminal-event ${item.direction}`}>
                      {item.direction === 'in' ? 'Vào ca' : 'Ra ca'}
                    </span>
                    <time dateTime={item.server_time}>
                      {new Date(item.server_time).toLocaleTimeString('vi-VN', {
                        timeZone: context?.batch.timezone || 'Asia/Ho_Chi_Minh',
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

        <p className="terminal-session-note">
          Mẫu mặt chỉ dùng cho ca/đợt này và hết hạn 48 giờ sau khi kết thúc ca.
        </p>
      </aside>

      {/* Bottom Bar Controls & Progress */}
      <div className="capture-bottom">
        <div
          className={`terminal-result ${receipt ? 'has-receipt' : ''}`}
          role="status"
          aria-live="polite"
        >
          <div className={`terminal-result-icon ${state.phase === 'success' ? 'valid' : ''}`}>
            {state.phase === 'success' ? '✓' : camera ? '◎' : '⚡'}
          </div>

          <div className="kiosk-progress">
            <div className="progress-title-row">
              <strong>
                {receipt && state.phase === 'success'
                  ? `${receipt.worker_name} (${receipt.worker_code})`
                  : camera
                    ? phaseTitles[state.phase]
                    : 'Camera đối tác đang tắt'}
              </strong>
            </div>

            <p className="feedback-message">
              {camera ? state.feedback : 'Camera đang tắt. Bật camera để quét tự động.'}
            </p>
          </div>

          {audioMessage && (
            <button className="secondary-pill-btn" onClick={() => void testSound()}>
              🔊 Bật âm thanh và nghe thử
            </button>
          )}
        </div>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {audioMessage && (
          <p className="audio-feedback" role="status">
            {audioMessage}
          </p>
        )}
        {context?.batch.rules.functional_trial && (
          <p className="partner-privacy-banner">
            ⚠️ Đang chạy thử chức năng. Chưa nghiệm thu độ chính xác theo nhóm hoặc chống ảnh giả; dữ liệu thử không dùng
            làm chứng từ thanh toán.
          </p>
        )}
      </div>

      {/* Partner Name Verification Dialog */}
      {camera && worker && ['pending', 'expired'].includes(worker.state) && (
        <PartnerNameDialog
          worker={worker}
          phase={state.phase}
          name={name}
          voice={voice}
          busy={nameBusy}
          message={voiceMessage}
          feedback={state.feedback}
          stream={stream.current}
          onName={value => {
            cancelVoice();
            setName(value);
            setSource(source === 'voice' || source === 'voice_edited' ? 'voice_edited' : 'manual');
          }}
          onRead={() => void readName()}
          onStopRead={() => recorder.current.finish()}
          onManual={() => {
            cancelVoice();
            setVoiceMessage('');
          }}
          onConfirm={() => void confirm()}
          onCancel={() => {
            cancelVoice();
            flow.current?.cancel();
          }}
        />
      )}

      {/* Pairing Modal Dialog */}
      {pairing && (
        <div className="demo-modal-backdrop" onClick={() => setPairing(false)}>
          <div
            className="demo-modal-dialog kiosk-pairing-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="pair-partner-kiosk-title"
            onClick={e => e.stopPropagation()}
          >
            <div className="demo-modal-header">
              <div>
                <h3 id="pair-partner-kiosk-title">Ghép quyền chấm công cho trình duyệt</h3>
                <p>Lấy mã 8 chữ số tại Quản trị → Thiết bị Kiosk.</p>
              </div>
              <button
                className="modal-close-btn"
                aria-label="Đóng ghép kiosk"
                onClick={() => setPairing(false)}
              >
                ✕
              </button>
            </div>
            <div className="demo-modal-body">
              <PairingPanel
                initiallyOpen
                allowRePair
                onDevice={next => onDeviceChange(next)}
                onPaired={() => setPairing(false)}
              />
              <a className="primary-pill-btn" href="#admin/devices" onClick={() => setPairing(false)}>
                Lấy mã ghép 8 số trong Quản trị → Thiết bị Kiosk
              </a>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
