import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { initMockApi } from './mockApi';
import './style.css';
import './admin.css';
import './terminal.css';
import './kiosk.css';
import { AdminPanel } from './AdminPanel';
import { KioskCapture, type KioskStatus } from './KioskCapture';
import type { KioskDevice } from './PairingPanel';

// Initialize in-browser mock API services for local standalone runtime
try {
  initMockApi();
} catch (err) {
  console.warn('initMockApi warning:', err);
}

function App() {
  const [status, setStatus] = useState<KioskStatus | null>(null);
  const [now, setNow] = useState(new Date());
  const [view, setView] = useState<'kiosk' | 'admin'>(location.hash === '#admin' ? 'admin' : 'kiosk');
  const [device, setDevice] = useState<KioskDevice | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
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

    const hash = () => setView(location.hash === '#admin' ? 'admin' : 'kiosk');
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
        }
      } catch {
        // Kiosk continues with local fallbacks
      }
    };
    void fetchDevice();
    const timer = setInterval(fetchDevice, 10000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, []);

  const timezone = status?.timezone || 'Asia/Ho_Chi_Minh';
  const hour = Number(new Intl.DateTimeFormat('en-GB', { hour: '2-digit', hourCycle: 'h23', timeZone: timezone }).format(now));
  const greeting = hour < 11 ? 'Chào buổi sáng!' : hour < 14 ? 'Chào buổi trưa!' : hour < 18 ? 'Chào buổi chiều!' : 'Chào buổi tối!';

  function changeView(next: 'kiosk' | 'admin') {
    setView(next);
    location.hash = next === 'admin' ? 'admin' : 'kiosk';
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  }

  async function handleDirectionChange(nextDir: 'in' | 'out') {
    if (device) {
      setDevice({ ...device, direction: nextDir });
      try {
        await fetch('/api/kiosk/device', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ direction: nextDir }),
        });
      } catch {
        // ignore
      }
    }
  }

  return (
    <div className={`shell ${view === 'kiosk' ? 'terminal-shell' : 'admin-shell-wrapper'}`}>
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
          <span className="mark">CC</span>
          <div className="brand-text">
            <span className="brand-title">Chấm Công AI</span>
            <span className="brand-sub">Điểm danh nhận diện khuôn mặt nội bộ</span>
          </div>
        </a>

        {/* View Segmented Tabs on Desktop & Tablet */}
        <nav className="view-nav hidden-on-mobile" aria-label="Điều hướng ứng dụng">
          <button
            className={`nav-tab-btn ${view === 'kiosk' ? 'selected' : ''}`}
            onClick={() => changeView('kiosk')}
          >
            <span className="nav-icon">📷</span> Chấm công (Kiosk)
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
              <span className="eyebrow">ĐIỂM CHẤM CÔNG TABLET</span>
              <span className="terminal-device-badge">
                <span className={`terminal-led ${status ? 'online' : ''}`} />
                {device?.paired ? (device.direction === 'in' ? 'Vào ca' : 'Ra ca') : 'Sẵn sàng'}
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
                <span>⏱</span> Ca hành chính: 08:00 – 17:00
              </div>
            </div>

            <div className="kiosk-instructions">
              <div className="step-item">
                <span className="step-num">1</span>
                <span>Đứng cách camera 0.5m – 1.2m</span>
              </div>
              <div className="step-item">
                <span className="step-num">2</span>
                <span>Nhìn thẳng và giữ yên trong 1 giây</span>
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
          <KioskCapture status={status} device={device} onDirectionChange={handleDirectionChange} />
        </main>
      )}

      {/* Mobile Bottom Navigation Bar (Visible only on mobile smartphones for thumb ergonomics) */}
      <nav className="mobile-bottom-nav" aria-label="Thanh điều hướng di động">
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
          <strong>CHẤM CÔNG LOCAL TABLET</strong>
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
