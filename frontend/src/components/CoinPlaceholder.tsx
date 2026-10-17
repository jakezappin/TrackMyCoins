import { useId } from "react";

interface Props {
  /** e.g. "1881-S". Omit for the small table version. */
  date?: string;
  /** e.g. "Morgan Dollar" */
  typeName?: string;
  /** Small caption at the bottom; empty to hide. */
  note?: string;
  className?: string;
}

/**
 * Stand-in artwork for a coin with no photos: a generic silver dollar with the coin's date.
 * Purely illustrative; not a depiction of any real coin design.
 */
export default function CoinPlaceholder({ date, typeName, className, note = "NO PHOTO YET" }: Props) {
  const id = useId().replace(/:/g, "");
  const detailed = Boolean(date);
  const stars = Array.from({ length: 13 }, (_, i) => {
    // Arc of stars across the top, like many US silver dollars.
    const a = Math.PI * (0.92 + (i / 12) * 1.16);
    return { x: 100 + 70 * Math.cos(a), y: 100 + 70 * Math.sin(a) };
  });

  return (
    <svg viewBox="0 0 200 200" className={className} role="img" aria-label={date ? `${date} placeholder` : "No photo"}>
      <defs>
        <radialGradient id={`face-${id}`} cx="38%" cy="32%" r="75%">
          <stop offset="0%" stopColor="#fbfbfa" />
          <stop offset="45%" stopColor="#d9dbde" />
          <stop offset="100%" stopColor="#9da2a8" />
        </radialGradient>
        <linearGradient id={`rim-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#eef0f2" />
          <stop offset="100%" stopColor="#7d838a" />
        </linearGradient>
      </defs>

      {/* Rim with reeding */}
      <circle cx="100" cy="100" r="96" fill={`url(#rim-${id})`} />
      <circle cx="100" cy="100" r="95" fill="none" stroke="#6f757c" strokeWidth="2.5" strokeDasharray="1.2 2.2" opacity="0.55" />
      {/* Field */}
      <circle cx="100" cy="100" r="86" fill={`url(#face-${id})`} />
      <circle cx="100" cy="100" r="86" fill="none" stroke="#8b9097" strokeWidth="1.2" opacity="0.6" />
      <circle cx="100" cy="100" r="80" fill="none" stroke="#ffffff" strokeWidth="0.8" opacity="0.7" />

      {stars.map((s, i) => (
        <path
          key={i}
          transform={`translate(${s.x} ${s.y}) scale(${detailed ? 0.42 : 0.6})`}
          d="M0,-10 L2.9,-3.1 L9.5,-3.1 L4.3,1.2 L6.2,8.1 L0,4 L-6.2,8.1 L-4.3,1.2 L-9.5,-3.1 L-2.9,-3.1 Z"
          fill="#8e939a"
          opacity="0.85"
        />
      ))}

      {detailed ? (
        <>
          <text x="100" y="98" textAnchor="middle" className="ph-date">
            {date}
          </text>
          {typeName && (
            <text x="100" y="122" textAnchor="middle" className="ph-type">
              {typeName.toUpperCase()}
            </text>
          )}
          {note && (
            <text x="100" y="158" textAnchor="middle" className="ph-note">
              {note}
            </text>
          )}
        </>
      ) : (
        <text x="100" y="118" textAnchor="middle" className="ph-dollar">
          $1
        </text>
      )}
    </svg>
  );
}
