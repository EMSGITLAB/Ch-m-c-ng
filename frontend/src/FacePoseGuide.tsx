import { useEffect, useId, useState } from 'react';
import './face-guide.css';

export type Pose = 'front' | 'left' | 'right' | 'up' | 'down';
export const poseLabels: Record<Pose, string> = { front: 'Nhìn thẳng', left: 'Quay trái', right: 'Quay phải', up: 'Nâng cằm', down: 'Hạ cằm' };
const front = { outline: 'M60 18 C85 18 100 41 98 76 C97 110 81 137 60 140 C39 137 23 110 22 76 C20 41 35 18 60 18 Z', nose: 'M60 78 L55 94 Q60 98 66 94', mouth: 'M45 111 Q60 118 75 111', eyes: [43, 70, 5, 77, 70, 5] };
const shapes = {
  front,
  left: { outline: 'M60 18 C81 18 96 41 95 76 C94 110 72 135 50 138 C31 135 22 109 22 76 C20 41 35 18 60 18 Z', nose: 'M45 76 L31 92 Q40 98 49 93', mouth: 'M34 110 Q47 117 61 110', eyes: [33, 70, 3, 65, 70, 5] },
  up: { outline: 'M60 23 C85 23 100 43 98 76 C97 107 81 128 60 131 C39 128 23 107 22 76 C20 43 35 23 60 23 Z', nose: 'M60 69 L54 81 Q60 87 67 81', mouth: 'M45 101 Q60 109 75 101', eyes: [43, 62, 5, 77, 62, 5] },
  down: { outline: 'M60 15 C85 15 100 39 98 76 C97 112 81 140 60 143 C39 140 23 112 22 76 C20 39 35 15 60 15 Z', nose: 'M60 91 L56 111 Q60 114 65 111', mouth: 'M47 123 Q60 128 73 123', eyes: [43, 84, 5, 77, 84, 5] },
};

function Movement({ attribute, from, to, enabled }: { attribute: string; from: string | number; to: string | number; enabled: boolean }) {
  return enabled ? <animate attributeName={attribute} values={`${from};${from};${to};${to};${from}`} keyTimes="0;0.18;0.48;0.78;1" dur="3.2s" repeatCount="indefinite" /> : null;
}

export function FacePoseGuide({ pose }: { pose: Pose }) {
  const gradient = useId().replace(/:/g, '');
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  const target = shapes[pose === 'right' ? 'left' : pose];
  const motion = pose !== 'front' && !reduced;
  return <figure className="face-pose-demo" aria-label={`Khuôn mặt minh họa: ${poseLabels[pose]}. Trái và phải là phía của bạn trong hình gương.`}>
    <svg key={pose} viewBox="0 0 140 170" role="img" aria-label={poseLabels[pose]}>
      <defs><linearGradient id={gradient} x1="0" y1="0" x2="1" y2=".8"><stop stopColor="#ecf5e4" /><stop offset="1" stopColor="#bad5ad" /></linearGradient></defs>
      <path d="M21 29 V17 Q21 9 29 9 H41 M99 9 H111 Q119 9 119 17 V29 M119 137 V149 Q119 157 111 157 H99 M41 157 H29 Q21 157 21 149 V137" fill="none" stroke="#a2b996" strokeWidth="2" strokeLinecap="round" />
      <g transform={pose === 'right' ? 'translate(130 0) scale(-1 1)' : 'translate(10 0)'} fill="none" stroke="#3a6049" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d={target.outline} fill={`url(#${gradient})`}><Movement attribute="d" from={front.outline} to={target.outline} enabled={motion} /></path>
        {[0, 1].map(index => <ellipse key={index} cx={target.eyes[index * 3]} cy={target.eyes[index * 3 + 1]} rx={target.eyes[index * 3 + 2]} ry="3" fill="#3a6049" stroke="none">
          <Movement attribute="cx" from={front.eyes[index * 3]} to={target.eyes[index * 3]} enabled={motion} />
          <Movement attribute="cy" from={front.eyes[index * 3 + 1]} to={target.eyes[index * 3 + 1]} enabled={motion} />
          <Movement attribute="rx" from={front.eyes[index * 3 + 2]} to={target.eyes[index * 3 + 2]} enabled={motion} />
        </ellipse>)}
        <path d={target.nose} stroke="#6a8d70"><Movement attribute="d" from={front.nose} to={target.nose} enabled={motion} /></path>
        <path d={target.mouth}><Movement attribute="d" from={front.mouth} to={target.mouth} enabled={motion} /></path>
      </g>
    </svg>
    <figcaption>{pose === 'front' ? 'Giữ đầu thẳng' : 'Làm theo khuôn mặt mẫu'}</figcaption>
  </figure>;
}

function ellipseArc(start: number, end: number, rx: number, ry: number) {
  const point = (angle: number) => `${150 + rx * Math.cos(angle)},${200 + ry * Math.sin(angle)}`;
  return `M${point(start)} A${rx},${ry} 0 0 1 ${point(end)}`;
}

export function CameraFaceFrame({ count, pose, active = true, steady = false, caption }: { count: number; pose: Pose | null; active?: boolean; steady?: boolean; caption?:string }) {
  const direction = { left: [2.48, 3.8], right: [-.66, .66], up: [4.05, 5.38], down: [.9, 2.23], front: [0, 0] };
  const arc = pose && pose !== 'front' ? direction[pose] : null;
  return <div className={`camera-face-frame${steady ? ' is-steady' : ''}`} aria-hidden="true">
    <div className="face-frame-shade" />
    <svg viewBox="0 0 300 400" preserveAspectRatio="xMidYMid meet">
      {steady && <ellipse cx="150" cy="200" rx="110" ry="161" className="frame-steady" />}
      {Array.from({ length: 10 }, (_, index) => <path key={index} d={ellipseArc(-Math.PI / 2 + index * Math.PI / 5 + .035, -Math.PI / 2 + (index + 1) * Math.PI / 5 - .035, 118, 169)} className={index < count ? 'frame-segment complete' : 'frame-segment'} />)}
      {arc && <path d={ellipseArc(arc[0], arc[1], 130, 184)} className="frame-direction" />}
    </svg>
    <div className="face-frame-caption">{caption || (count >= 10 ? 'Đủ 10 mẫu đạt' : active ? 'Đặt khuôn mặt trong khung' : 'Xem tư thế mẫu rồi bật camera')}</div>
  </div>;
}
