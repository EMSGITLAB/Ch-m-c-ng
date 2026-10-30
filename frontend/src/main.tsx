import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import './admin.css';
import './terminal.css';
import './kiosk.css';
import './gemini-integration.css';
import { AdminPanel } from './AdminPanel';
import { KioskCapture, type KioskStatus } from './KioskCapture';
import { PartnerKioskCapture } from './PartnerKioskCapture';
import type { KioskDevice } from './PairingPanel';

function App() {
  const [status, setStatus] = useState<KioskStatus | null>(null);
  const [now, setNow] = useState(new Date());
  const readView=(): 'kiosk'|'admin'|'partner'=>location.hash.startsWith('#admin')?'admin':location.hash.startsWith('#partner')?'partner':'kiosk';
  const [view, setView] = useState(readView);
  const [device, setDevice] = useState<KioskDevice | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [directionBusy, setDirectionBusy] = useState(false);
  const [deviceError, setDeviceError] = useState('');
  const serverClock = useRef<{ at: number; received: number } | null>(null);

  // Poll system status and maintain server time synchronization
  useEffect(() => {
    let disposed = false;
    let pending: AbortController | null = null;

    const check = async () => {
      pending?.abort();
      const request = new AbortController();
      pending = request;
      const timeout = setTimeout(() => request.abort(), 6000);
      try {
        const response = await fetch('/api/system/status', { signal: request.signal });
        if (!response.ok) throw new Error();
        const body = await response.json();
        const at = Date.parse(body.server_time);
        if (!Number.isFinite(at)) throw new Error();
        if (!disposed && pending === request) {
          serverClock.current = { at, received: performance.now() };
          setNow(new Date(at));
          setStatus(body);
        }
      } catch {
        if (!disposed && pending === request) setStatus(null);
      } finally {
        clearTimeout(timeout);
      }
    };

    void check();
    const poll = setInterval(check, 10000);
    const clock = setInterval(() => {
      const anchor = serverClock.current;
      if (anchor) setNow(new Date(anchor.at + performance.now() - anchor.received));
    }, 1000);

    const hash = () => setView(readView());
    window.addEventListener('hashchange', hash);

    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);

    return () => {
      disposed = true;
      pending?.abort();
      clearInterval(poll);
      clearInterval(clock);
      window.removeEventListener('hashchange', hash);
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);

  // Seamlessly load active kiosk device in background (No pairing forms shown to normal users)
  useEffect(() => {
    let disposed = false;
    const fetchDevice = async () => {
      try {
        const response = await fetch('/api/kiosk/device');
        if (response.ok) {
          const dev = await response.json();
          if (!disposed) setDevice(dev);
        } else if (response.status === 401 && !disposed) setDevice(null);
      } catch {
        // Kiosk continues with local fallbacks
      }
    };
    window.addEventListener('kiosk-device-changed', fetchDevice);
    void fetchDevice();
    const timer = setInterval(fetchDevice, 10000);
    return () => {
      disposed = true;
      clearInterval(timer);
      window.removeEventListener('kiosk-device-changed', fetchDevice);
    };
  }, []);

  const timezone = status?.timezone || 'Asia/Ho_Chi_Minh';
  const hour = Number(new Intl.DateTimeFormat('en-GB', { hour: '2-digit', hourCycle: 'h23', timeZone: timezone }).format(now));
  const greeting = hour < 11 ? 'Chào buổi sáng!' : hour < 14 ? 'Chào buổi trưa!' : hour < 18 ? 'Chào buổi chiều!' : 'Chào buổi tối!';

  function changeView(next: 'kiosk' | 'admin' | 'partner') {
    setView(next);
    location.hash = next;
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  }

  async function handleDirectionChange(nextDir: 'in' | 'out') {
    if (!device?.paired || directionBusy || device.direction === nextDir) return;
    setDirectionBusy(true); setDeviceError('');
    try {
      const response = await fetch('/api/kiosk/device', { method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-Kiosk-Intent': 'change-direction' },
        body: JSON.stringify({direction: nextDir}), signal: AbortSignal.timeout(15000) });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Chưa đổi được chiều chấm công.');
      setDevice(body);
    } catch (e) { setDeviceError(e instanceof Error ? e.message : 'Chưa đổi được chiều chấm công.'); }
    finally { setDirectionBusy(false); }
  }

  return (
    <div className={`shell ${view !== 'admin' ? 'terminal-shell' : 'admin-shell-wrapper'}`}>
      {/* Top Header Bar */}
      <header className="app-header">
        <a
          className="brand"
          href="/"
          onClick={e => {
            e.preventDefault();
            changeView('kiosk');
          }}
        >
          <img className="mark" src="/brand/ontime-mark-dark.svg" alt="" width="44" height="44" />
          <div className="brand-text">
            <span className="brand-title">OnTime</span>
            <span className="brand-sub">Chấm công khuôn mặt</span>
          </div>
        </a>

        {/* View Segmented Tabs on Desktop & Tablet */}
        <nav className="view-nav hidden-on-mobile" aria-label="Điều hướng ứng dụng">
          <button className={`nav-tab-btn ${view==='partner'?'selected':''}`} onClick={()=>changeView('partner')}>Chấm công đối tác</button>
          <button
            className={`nav-tab-btn ${view === 'kiosk' ? 'selected' : ''}`}
            onClick={() => changeView('kiosk')}
          >
            <span className="nav-icon">📷</span> Chấm công nội bộ
          </button>
          <button
            className={`nav-tab-btn ${view === 'admin' ? 'selected' : ''}`}
            onClick={() => changeView('admin')}
          >
            <span className="nav-icon">🔒</span> Quản trị (Admin)
          </button>
        </nav>

        {/* Right Header Status & Tablet Quick Toggles */}
        <div className="header-right-actions">
          <button
            className="fullscreen-toggle-btn"
            onClick={toggleFullscreen}
            title={isFullscreen ? 'Thoát toàn màn hình' : 'Mở toàn màn hình cho Tablet'}
          >
            {isFullscreen ? '⤓ Thu nhỏ' : '⛶ Toàn màn hình'}
          </button>

          <button
            className="mobile-admin-lock-btn"
            onClick={() => changeView(view === 'admin' ? 'kiosk' : 'admin')}
            title="Đăng nhập quản trị"
          >
            {view === 'admin' ? '📷 Về Kiosk' : '🔒 Quản trị'}
          </button>

          <span className="connection-badge">
            <i className={status ? 'online pulse' : ''} />
            <span className="connection-text">{status ? 'Trực tuyến' : 'Đang kết nối…'}</span>
          </span>
        </div>
      </header>

      {/* Main Screen Content */}
      {view === 'admin' ? (
        <AdminPanel />
      ) : (
        <main className="terminal-main">
          {/* Left Kiosk Info & Clock Card (Hidden on narrow mobile, prominent on Tablet & iPad) */}
          <section className="intro terminal-clock" aria-label="Đồng hồ và thông tin ca làm việc">
            <div className="clock-eyebrow-row">
              <span className="eyebrow">{view==='partner'?'ĐIỂM CHẤM CÔNG ĐỐI TÁC':'ĐIỂM CHẤM CÔNG TABLET'}</span>
              <span className="terminal-device-badge">
                <span className={`terminal-led ${status ? 'online' : ''}`} />
                {device?.paired ? (device.direction === 'in' ? 'Vào ca' : 'Ra ca') : 'Chưa ghép quyền'}
              </span>
            </div>

            <h1 className="greeting-text">{greeting}</h1>

            <div className="clock-card">
              <div className="clock-digits">
                {status
                  ? now.toLocaleTimeString('vi-VN', {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                      timeZone: timezone,
                    })
                  : '--:--:--'}
              </div>
              <div className="clock-date">
                {now.toLocaleDateString('vi-VN', {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                  timeZone: timezone,
                })}
              </div>
              <div className="clock-shift-pill">
                <span>⏱</span> {view==='partner'?'Theo đợt đã gán cho thiết bị':'Giờ tham chiếu: 08:00 – 17:00'}
              </div>
            </div>

            <div className="kiosk-instructions">
              <div className="step-item">
                <span className="step-num">1</span>
                <span>Đứng cách camera 0.5m – 1.2m</span>
              </div>
              <div className="step-item">
                <span className="step-num">2</span>
                <span>Nhìn thẳng và giữ yên trong giây lát</span>
              </div>
              <div className="step-item">
                <span className="step-num">3</span>
                <span>Nghe tiếng chuông "Hợp lệ" và xem kết quả</span>
              </div>
            </div>

            <div className="privacy-card">
              <span className="privacy-icon">🛡️</span>
              <div>
                <strong>Bảo mật sinh trắc học cục bộ</strong>
                <p>Xử lý 100% tại thiết bị nội bộ, không tải ảnh hoặc vector lên đám mây ngoài.</p>
              </div>
            </div>
          </section>

          {/* Center/Right Biometric Camera & Attendance Component */}
          {view==='partner'?<PartnerKioskCapture device={device} onDirectionChange={handleDirectionChange} onDeviceChange={setDevice} directionBusy={directionBusy}/>:device?.workflow==='partner'?<section className="partner-card"><h2>Thiết bị đang dành cho đợt đối tác</h2><p>Mở đúng phân hệ để tiếp tục quét Vào/Ra.</p><button className="primary" onClick={()=>changeView('partner')}>Mở Chấm công đối tác</button></section>:<KioskCapture status={status} device={device} onDirectionChange={handleDirectionChange} onDeviceChange={setDevice} directionBusy={directionBusy} />}
          {deviceError && <p className="error" role="alert">{deviceError}</p>}
        </main>
      )}

      {/* Mobile Bottom Navigation Bar (Visible only on mobile smartphones for thumb ergonomics) */}
      <nav className="mobile-bottom-nav" aria-label="Thanh điều hướng di động">
        <button className={`mobile-tab-btn ${view==='partner'?'active':''}`} onClick={()=>changeView('partner')}><span className="mobile-tab-icon">👥</span><span className="mobile-tab-label">Đối tác</span></button>
        <button
          className={`mobile-tab-btn ${view === 'kiosk' ? 'active' : ''}`}
          onClick={() => changeView('kiosk')}
        >
          <span className="mobile-tab-icon">📷</span>
          <span className="mobile-tab-label">Chấm công</span>
        </button>

        <button
          className="mobile-tab-btn"
          onClick={() => {
            if (view !== 'kiosk') changeView('kiosk');
            setTimeout(() => {
              document.querySelector('.terminal-recent')?.scrollIntoView({ behavior: 'smooth' });
            }, 100);
          }}
        >
          <span className="mobile-tab-icon">📋</span>
          <span className="mobile-tab-label">Vừa ghi nhận</span>
        </button>

        <button
          className={`mobile-tab-btn ${view === 'admin' ? 'active' : ''}`}
          onClick={() => changeView('admin')}
        >
          <span className="mobile-tab-icon">🔒</span>
          <span className="mobile-tab-label">Quản trị</span>
        </button>
      </nav>

      {/* App Footer */}
      <footer className="app-footer">
        <div className="footer-left">
          <strong>OnTime</strong>
          {device && <span> · {device.name}</span>}
        </div>
        <div className="footer-right">
          <span>Phiên bản {status?.version || '0.2.0'}</span>
          <span> · Múi giờ {timezone}</span>
          <span> · 100% Offline Bảo mật</span>
        </div>
      </footer>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
