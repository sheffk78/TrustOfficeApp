import React from 'react';

/**
 * Reusable circular health score ring.
 *
 * Props:
 *  - score (int)
 *  - maxScore (int, default 115)
 *  - size ('sm' | 'md' | 'lg') -> 60 / 120 / 200 px
 *  - showLabel (bool) — show "score / maxScore" text in center
 */
export default function HealthScoreDisplay({
  score = 0,
  maxScore = 115,
  size = 'md',
  showLabel = true,
}) {
  const px = size === 'sm' ? 60 : size === 'lg' ? 200 : 120;
  const strokeWidth = size === 'sm' ? 6 : size === 'lg' ? 12 : 9;
  const radius = (px - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  const clamped = Math.max(0, Math.min(score || 0, maxScore));
  const pct = maxScore > 0 ? clamped / maxScore : 0;
  const dashOffset = circumference * (1 - pct);

  const color =
    clamped >= 96
      ? 'var(--success, #16a34a)'
      : clamped >= 72
      ? 'var(--warning, #d97706)'
      : 'var(--error, #dc2626)';

  const textClass =
    clamped >= 96 ? 'text-success' : clamped >= 72 ? 'text-warning' : 'text-error';

  const scoreFontSize =
    size === 'sm' ? 'text-sm' : size === 'lg' ? 'text-5xl' : 'text-2xl';
  const labelFontSize = size === 'sm' ? 'text-[8px]' : 'text-[10px]';

  return (
    <div
      className="inline-flex flex-col items-center justify-center"
      style={{ width: px, height: px }}
      data-testid={`health-score-display-${size}`}
    >
      <div className="relative" style={{ width: px, height: px }}>
        <svg
          width={px}
          height={px}
          viewBox={`0 0 ${px} ${px}`}
          className="transform -rotate-90"
        >
          {/* Track */}
          <circle
            cx={px / 2}
            cy={px / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeOpacity="0.12"
            strokeWidth={strokeWidth}
          />
          {/* Progress */}
          <circle
            cx={px / 2}
            cy={px / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            style={{
              transition: 'stroke-dashoffset 0.8s ease-in-out, stroke 0.4s ease-in-out',
            }}
          />
        </svg>
        {showLabel && (
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`font-mono font-semibold leading-none ${scoreFontSize} ${textClass}`}>
              {clamped}
            </span>
            {size !== 'sm' && (
              <span
                className={`font-mono uppercase tracking-widest text-muted-foreground mt-1 ${labelFontSize}`}
              >
                / {maxScore}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
