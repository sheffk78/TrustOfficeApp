import React, { useMemo, useState } from 'react';
import { format, parseISO } from 'date-fns';

/**
 * Pure-SVG health trend line chart — polished version.
 *
 * Props:
 *  - data: array of { date, score, color? }
 *  - height (default 200)
 *  - width (default 600) — used for viewBox aspect; container renders at 100% width
 *  - maxScore (default 115)
 */
export default function HealthTrendChart({
  data = [],
  height = 200,
  width = 600,
  maxScore = 115,
}) {
  const [hover, setHover] = useState(null); // {index, x, y, date, score}

  // Chart padding inside the viewBox
  const padL = 36;
  const padR = 16;
  const padT = 14;
  const padB = 28;

  const innerW = width - padL - padR;
  const innerH = height - padT - padB;

  const yFor = (score) => padT + innerH - (score / maxScore) * innerH;
  const xFor = (i, n) => padL + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);

  const points = useMemo(() => {
    if (!data || data.length === 0) return [];
    return data.map((d, i) => ({
      x: xFor(i, data.length),
      y: yFor(Math.max(0, Math.min(d.score || 0, maxScore))),
      date: d.date,
      score: d.score || 0,
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, width, height, maxScore]);

  // Smooth cubic-bezier line path
  const linePath = useMemo(() => {
    if (points.length === 0) return '';
    if (points.length === 1) return `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;

    const tension = 0.3; // smoothness factor
    const path = [`M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`];

    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i];
      const p1 = points[i + 1];
      const prevX = i > 0 ? points[i - 1].x : p0.x;
      const nextY = i < points.length - 2 ? points[i + 2].y : p1.y;
      const nextX = i < points.length - 2 ? points[i + 2].x : p1.x;

      const cp1x = p0.x + (p1.x - prevX) * tension;
      const cp1y = p0.y + (p1.y - (i > 0 ? points[i - 1].y : p0.y)) * tension;
      const cp2x = p1.x - (nextX - p0.x) * tension;
      const cp2y = p1.y - (nextY - p0.y) * tension;

      path.push(`C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p1.x.toFixed(2)} ${p1.y.toFixed(2)}`);
    }
    return path.join(' ');
  }, [points]);

  // Smooth area fill path (mirrors the line path, closes to bottom)
  const areaPath = useMemo(() => {
    if (points.length === 0) return '';
    const baseY = (padT + innerH).toFixed(2);
    if (points.length === 1) {
      return `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)} L ${points[0].x.toFixed(2)} ${baseY} Z`;
    }
    // Use the same smooth path then close to bottom
    const top = linePath;
    const lastX = points[points.length - 1].x.toFixed(2);
    const firstX = points[0].x.toFixed(2);
    return `${top} L ${lastX} ${baseY} L ${firstX} ${baseY} Z`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linePath, points]);

  // Determine dominant line color from latest point
  const latestScore = points.length ? points[points.length - 1].score : 0;
  const lineColor =
    latestScore >= 96 ? '#16a34a' : latestScore >= 72 ? '#d97706' : '#dc2626';

  // Unique gradient ID to avoid collisions if multiple charts rendered
  const gradId = useMemo(() => `healthTrendFill_${Math.random().toString(36).slice(2, 9)}`, []);
  const glowId = useMemo(() => `healthTrendGlow_${Math.random().toString(36).slice(2, 9)}`, []);

  // X-axis tick labels: up to ~6 evenly spaced
  const tickCount = Math.min(6, points.length);
  const tickIndexes = useMemo(() => {
    if (points.length === 0) return [];
    if (points.length <= tickCount) return points.map((_, i) => i);
    const idxs = [];
    for (let i = 0; i < tickCount; i++) {
      idxs.push(Math.round((i / (tickCount - 1)) * (points.length - 1)));
    }
    return Array.from(new Set(idxs));
  }, [points, tickCount]);

  const safeFormat = (d) => {
    try {
      return format(parseISO(d), 'MMM d');
    } catch {
      return d;
    }
  };

  // Zone band Y positions
  const y96 = yFor(96);
  const y72 = yFor(72);
  const y0 = yFor(0);
  const yTop = yFor(maxScore);

  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-muted-foreground border border-dashed border-navy/10 rounded"
        style={{ height }}
        data-testid="health-trend-empty"
      >
        No trend data available yet
      </div>
    );
  }

  return (
    <div className="w-full relative" data-testid="health-trend-chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="w-full"
        style={{ height, display: 'block' }}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          {/* Area fill gradient — fades from line color to transparent */}
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.25" />
            <stop offset="60%" stopColor={lineColor} stopOpacity="0.08" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
          </linearGradient>

          {/* Soft glow filter for data points */}
          <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Zone bands — subtle health/at-risk/critical backgrounds */}
        <rect
          x={padL}
          y={yTop}
          width={innerW}
          height={Math.max(0, y96 - yTop)}
          fill="#16a34a"
          opacity="0.08"
        />
        <rect
          x={padL}
          y={y96}
          width={innerW}
          height={Math.max(0, y72 - y96)}
          fill="#d97706"
          opacity="0.08"
        />
        <rect
          x={padL}
          y={y72}
          width={innerW}
          height={Math.max(0, y0 - y72)}
          fill="#dc2626"
          opacity="0.08"
        />

        {/* Zone divider lines — more refined than dashed gridlines */}
        <line
          x1={padL}
          x2={padL + innerW}
          y1={y96}
          y2={y96}
          stroke="#16a34a"
          strokeOpacity="0.3"
          strokeWidth="1"
        />
        <line
          x1={padL}
          x2={padL + innerW}
          y1={y72}
          y2={y72}
          stroke="#d97706"
          strokeOpacity="0.3"
          strokeWidth="1"
        />

        {/* Y-axis labels */}
        {[maxScore, 96, 72, 0].map((v) => (
          <text
            key={v}
            x={padL - 8}
            y={yFor(v) + 3}
            fontSize="9"
            textAnchor="end"
            fill="currentColor"
            opacity="0.45"
            className="font-mono"
          >
            {v}
          </text>
        ))}

        {/* Area fill — smooth gradient under the curve */}
        <path d={areaPath} fill={`url(#${gradId})`} stroke="none" />

        {/* Line — smooth bezier curve with subtle shadow */}
        <path
          d={linePath}
          fill="none"
          stroke={lineColor}
          strokeWidth="2.5"
          strokeLinejoin="round"
          strokeLinecap="round"
          opacity="0.9"
        />

        {/* Data points — larger with white halo and glow on hover */}
        {points.map((p, i) => {
          const isHovered = hover && hover.index === i;
          const isLast = i === points.length - 1;
          return (
            <g key={i}>
              {/* White halo ring */}
              <circle
                cx={p.x}
                cy={p.y}
                r={isHovered ? 6 : isLast ? 5 : 3.5}
                fill="#fff"
                opacity="0.95"
              />
              {/* Colored dot */}
              <circle
                cx={p.x}
                cy={p.y}
                r={isHovered ? 4 : isLast ? 3 : 2}
                fill={lineColor}
                filter={isHovered ? `url(#${glowId})` : undefined}
              />
              {/* Invisible hover target */}
              <rect
                x={p.x - innerW / Math.max(1, points.length) / 2}
                y={padT}
                width={innerW / Math.max(1, points.length)}
                height={innerH}
                fill="transparent"
                onMouseEnter={() => setHover({ index: i, ...p })}
              >
                <title>{`${safeFormat(p.date)} — Score: ${p.score}`}</title>
              </rect>
            </g>
          );
        })}

        {/* X-axis labels */}
        {tickIndexes.map((i) => (
          <text
            key={i}
            x={points[i].x}
            y={padT + innerH + 18}
            fontSize="9"
            textAnchor="middle"
            fill="currentColor"
            opacity="0.45"
            className="font-mono"
          >
            {safeFormat(points[i].date)}
          </text>
        ))}

        {/* Hover crosshair */}
        {hover && (
          <line
            x1={hover.x}
            x2={hover.x}
            y1={padT}
            y2={padT + innerH}
            stroke={lineColor}
            strokeOpacity="0.35"
            strokeWidth="1"
            strokeDasharray="3 3"
          />
        )}
      </svg>

      {/* Custom tooltip */}
      {hover && (
        <div
          className="absolute pointer-events-none bg-popover text-popover-foreground border border-border rounded-md px-2.5 py-1.5 text-xs shadow-lg z-10 transition-opacity"
          style={{
            left: `${(hover.x / width) * 100}%`,
            top: `${(hover.y / height) * 100}%`,
            transform: 'translate(-50%, -130%)',
            whiteSpace: 'nowrap',
          }}
        >
          <span className="font-mono font-semibold text-sm">{hover.score}</span>
          <span className="text-muted-foreground ml-2">{safeFormat(hover.date)}</span>
        </div>
      )}
    </div>
  );
}