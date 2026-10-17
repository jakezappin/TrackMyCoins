import { useId } from "react";

/** TrackMyCoins mark: a silver coin with a reeded rim and a gold check. */
export function LogoMark({ size = 28 }: { size?: number }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden className="logo-mark">
      <defs>
        <radialGradient id={`lm-face-${id}`} cx="35%" cy="30%" r="80%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="50%" stopColor="#d6d9de" />
          <stop offset="100%" stopColor="#8f959c" />
        </radialGradient>
        <linearGradient id={`lm-gold-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#f3d27a" />
          <stop offset="100%" stopColor="#b8892b" />
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="#7d838a" />
      <circle cx="32" cy="32" r="29.2" fill="none" stroke="#5f656c" strokeWidth="1.6" strokeDasharray="0.9 1.6" />
      <circle cx="32" cy="32" r="26" fill={`url(#lm-face-${id})`} />
      <circle cx="32" cy="32" r="21.5" fill="none" stroke="#9aa0a7" strokeWidth="1" opacity="0.7" />
      <path
        d="M20.5 33.5 L28.5 41.5 L44 24"
        fill="none"
        stroke={`url(#lm-gold-${id})`}
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Mark + "TrackMyCoins" wordmark. `tone="light"` for dark backgrounds. */
export default function Logo({ size = 28, tone = "auto" }: { size?: number; tone?: "auto" | "light" }) {
  return (
    <span className={`logo logo-${tone}`}>
      <LogoMark size={size} />
      <span className="logo-word">
        Track<span className="logo-my">My</span>
        <span className="logo-coins">Coins</span>
      </span>
    </span>
  );
}
