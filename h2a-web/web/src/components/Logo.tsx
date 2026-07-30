import { useId } from 'react';

/** H2A mark — an ascending flow-arrow that reads as an "A" (Apex) with an AI spark
 *  at its apex, on an aurora (teal→blue→violet) squircle. Scales for favicon → hero. */
export default function Logo({ size = 40, glow = false }: { size?: number; glow?: boolean }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" role="img" aria-label="H2A"
      style={glow ? { filter: `drop-shadow(0 6px 20px rgba(52,226,192,.35))` } : undefined}>
      <defs>
        <linearGradient id={`g${id}`} x1="5" y1="4" x2="43" y2="44" gradientUnits="userSpaceOnUse">
          <stop stopColor="#3EE9C6" />
          <stop offset=".52" stopColor="#37B6F0" />
          <stop offset="1" stopColor="#8B7BFF" />
        </linearGradient>
        <linearGradient id={`s${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop stopColor="#fff" stopOpacity=".28" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="3" y="3" width="42" height="42" rx="13" fill={`url(#g${id})`} />
      <rect x="3" y="3" width="42" height="20" rx="13" fill={`url(#s${id})`} />
      <path d="M13.5 33.5 L24 14.5 L34.5 33.5" stroke="#06121C" strokeWidth="3.4"
        strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18.7 27 H29.3" stroke="#06121C" strokeWidth="3.4" strokeLinecap="round" />
      <circle cx="24" cy="14.5" r="3.2" fill="#06121C" />
      <circle cx="24" cy="14.5" r="1.5" fill="#5FF3D6" />
    </svg>
  );
}
