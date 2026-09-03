import { useId } from 'react';

/**
 * The Portage mark — a payload carried from one platform to another.
 *
 * Three iterations of reasoning got here. The original drew an "A" for Apex, which
 * stopped being true the moment a second target existed: a logo naming one of two
 * destinations quietly says the other is a guest. The replacement drew a symmetric arc,
 * which reads as a *bridge* — a thing that sits between two places without saying
 * anything about travel. A migration has a direction.
 *
 * So: a hollow source node at the left, a solid destination node at the right and
 * higher, and an arc that rises between them carrying a lit payload at its apex. Hollow
 * to solid is the direction, without an arrowhead — arrowheads disappear at 16px, and
 * this has to survive being a favicon.
 *
 * Same aurora squircle and ink as the original. The palette never changed.
 */
export default function Logo({ size = 40, glow = false }: { size?: number; glow?: boolean }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" role="img"
      aria-label="Portage"
      style={glow ? { filter: `drop-shadow(0 8px 24px rgba(52,226,192,.38))` } : undefined}>
      <defs>
        <linearGradient id={`g${id}`} x1="5" y1="4" x2="43" y2="44" gradientUnits="userSpaceOnUse">
          <stop stopColor="#3EE9C6" />
          <stop offset=".52" stopColor="#37B6F0" />
          <stop offset="1" stopColor="#8B7BFF" />
        </linearGradient>
        <linearGradient id={`s${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop stopColor="#fff" stopOpacity=".30" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>

      <rect x="3" y="3" width="42" height="42" rx="13" fill={`url(#g${id})`} />
      <rect x="3" y="3" width="42" height="21" rx="13" fill={`url(#s${id})`} />

      {/* the carry: source (low, hollow) → apex → destination (high, solid) */}
      <path d="M12 34.5 C 15.5 22, 21 16, 26 16 C 30.5 16, 33 20, 35.5 25.5"
        stroke="#06121C" strokeWidth="3.4" strokeLinecap="round" fill="none" />
      <circle cx="12" cy="34.5" r="4.6" fill="#06121C" />
      <circle cx="12" cy="34.5" r="2.1" fill={`url(#g${id})`} />
      <circle cx="35.5" cy="25.5" r="4.6" fill="#06121C" />
      <circle cx="25.6" cy="16.1" r="3.1" fill="#06121C" />
      <circle cx="25.6" cy="16.1" r="1.5" fill="#5FF3D6" />
    </svg>
  );
}
