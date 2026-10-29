import { useEffect, useState, type FormEvent } from 'react';

export type KioskDevice = { id: string; name: string; direction: 'in' | 'out'; active: boolean; paired: boolean };

export function PairingPanel({ onDevice }: { onDevice: (device: KioskDevice | null) => void }) {
  const [device, setDevice] = useState<KioskDevice | null>(null);
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    async function check() {
      try {
        const response = await fetch('/api/kiosk/device', { signal: controller.signal });
        if (response.status === 401) { setDevice(null); onDevice(null); }
        else if (response.ok) { const result = await response.json(); setDevice(result); onDevice(result); }
      } catch { /* Connection errors are shown by the main server status. */ }
    }
    check(); const timer = setInterval(check, 10000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);

  async function pair(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const response = await fetch('/api/kiosk/pair', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Kiosk-Intent': 'pair-local-kiosk' }, body: JSON.stringify({ code }), signal: AbortSignal.timeout(15000) });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Mã ghép cần đủ 8 chữ số.');
      setDevice(result); onDevice(result); setCode('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Không ghép được thiết bị.'); }
    finally { setBusy(false); }
  }

  if (device) return <div className="paired-device"><span className="notice-dot" /><span>{device.name} · {device.direction === 'in' ? 'Điểm vào ca' : 'Điểm ra ca'} · Đã ghép quyền</span></div>;
  return <details className="pairing-panel"><summary>Thiết lập điểm chấm công</summary><p>Lấy mã tại Quản trị → Thiết bị, rồi nhập một lần trên trình duyệt này.</p><form onSubmit={pair}><label>Mã ghép 8 số<input value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 8))} inputMode="numeric" pattern="[0-9]{8}" minLength={8} maxLength={8} autoComplete="off" required /></label><button disabled={busy}>{busy ? 'Đang ghép…' : 'Ghép thiết bị'}</button></form>{error && <div className="error" role="alert">{error}</div>}</details>;
}
