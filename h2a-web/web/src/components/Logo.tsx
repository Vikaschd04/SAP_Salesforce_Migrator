import { useId } from 'react';

/**
 * The Portage mark — two shores and the arc that carries a codebase between them.
 *
 * The old mark drew an "A" for Apex, which stopped being true the moment a second target
 * existed: a logo that names one of two destinations quietly says the other is a guest.
 * This one draws the *crossing* instead — a low node, a high node, and the lifted path
 * between, with the spark at its apex. It says nothing about which platforms are at
 * either end, which is the point.
 *
 * Same aurora squircle and ink as before: this is a rename, not a rebrand.
 */
export default function Logo({ size = 40, glow = false }: { size?: number; glow?: boolean }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" role="img"
      aria-label="Portage"
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

      {/* the crossing: source shore, lifted path, destination shore */}
      <path d="M11.5 33 C 17 33, 19 17.5, 24 17.5 C 29 17.5, 31 33, 36.5 33"
        stroke="#06121C" strokeWidth="3.3" strokeLinecap="round" fill="none" />
      <circle cx="11.5" cy="33" r="3.1" fill="#06121C" />
      <circle cx="36.5" cy="33" r="3.1" fill="#06121C" />
      <circle cx="24" cy="17.5" r="3.4" fill="#06121C" />
      <circle cx="24" cy="17.5" r="1.6" fill="#5FF3D6" />
    </svg>
  );
}
