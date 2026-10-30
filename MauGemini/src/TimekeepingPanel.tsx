import { useState } from 'react';
import { TimesheetsPanel } from './TimesheetsPanel';
import { AttendanceCorrections, PeriodControl } from './TimeControlsPanel';
import './time-controls.css';

export type TimekeepingProps = { csrf: string; onUnauthorized: () => void };
export function TimekeepingPanel(props: TimekeepingProps) {
  const [view, setView] = useState('preview');
  return <>
    <nav className="timekeeping-tabs" aria-label="Quản lý bảng công">
      <button className={view === 'preview' ? 'selected' : ''} onClick={() => setView('preview')}>Xem trước</button>
      <button className={view === 'corrections' ? 'selected' : ''} onClick={() => setView('corrections')}>Điều chỉnh công</button>
      <button className={view === 'periods' ? 'selected' : ''} onClick={() => setView('periods')}>Chốt kỳ & bản lưu</button>
    </nav>
    {view === 'preview' ? <TimesheetsPanel {...props} /> : view === 'corrections' ? <AttendanceCorrections {...props} /> : <PeriodControl {...props} />}
  </>;
}
