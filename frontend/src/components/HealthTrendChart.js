import React, { useMemo, useState } from 'react';
import { format, parseISO } from 'date-fns';

/**
 * Pure-SVG health trend line chart.
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
  const [hover, setHover] = useState(null); // {x, y, date, score}

  // Chart padding inside the viewBox
  const padL = 34;
  const padR = 12;
  const padT = 12;
  const padB = 26;

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

  const linePath = useMemo(() => {
    if (points.length === 0) return '';
    return points
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
      .join(' ');
  }, [points]);

  const areaPath = useMemo(() => {
    if (points.length === 0) return '';
    const top = points
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
      .join(' ');
    const lastX = points[points.length - 1].x.toFixed(2);
    const firstX = points[0].x.toFixed(2);
    const baseY = (padT + innerH).toFixed(2);
    return `${top} L ${lastX} ${baseY} L ${firstX} ${baseY} Z`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points]);

  // Determine dominant line color from latest point
  const latestScore = points.length ? points[points.length - 1].score : 0;
  const lineColor =
    latestScore >= 96 ? '#16a34a' : latestScore >= 72 ? '#d97706' : '#dc2626';

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

  // Zone bands
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
        preserveAspectRatio="none"
        className="w-full"
        style={{ height, display: 'block' }}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="healthTrendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.18" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* Zone bands */}
        <rect
          x={padL}
          y={yTop}
          width={innerW}
          height={Math.max(0, y96 - yTop)}
          fill="#16a34a"
          opacity="0.10"
        />
        <rect
          x={padL}
          y={y96}
          width={innerW}
          height={Math.max(0, y72 - y96)}
          fill="#d97706"
          opacity="0.10"
        />
        <rect
          x={padL}
          y={y72}
          width={innerW}
          height={Math.max(0, y0 - y72)}
          fill="#dc2626"
          opacity="0.10"
        />

        {/* Gridlines + Y labels */}
        {[0, 72, 96, maxScore].map((v) => (
          <g key={v}>
            <line
              x1={padL}
              x2={padL + innerW}
              y1={yFor(v)}
              y2={yFor(v)}
              stroke="currentColor"
              strokeOpacity="0.15"
              strokeDasharray="3 3"
            />
            <text
              x={padL - 6}
              y={yFor(v) + 3}
              fontSize="9"
              textAnchor="end"
              fill="currentColor"
              opacity="0.6"
              className="font-mono"
            >
              {v}
            </text>
          </g>
        ))}

        {/* Area fill */}
        <path d={areaPath} fill="url(#healthTrendFill)" stroke="none" />

        {/* Line */}
        <path
          d={linePath}
          fill="none"
          stroke={lineColor}
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Data points + hover targets */}
        {points.map((p, i) => (
          <g key={i}>
            <circle
              cx={p.x}
              cy={p.y}
              r={hover && hover.index === i ? 4 : 2.5}
              fill={lineColor}
              stroke="#fff"
              strokeWidth="1"
            />
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
        ))}

        {/* X-axis labels */}
        {tickIndexes.map((i) => (
          <text
            key={i}
            x={points[i].x}
            y={padT + innerH + 16}
            fontSize="9"
            textAnchor="middle"
            fill="currentColor"
            opacity="0.6"
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
            strokeOpacity="0.4"
            strokeDasharray="2 2"
          />
        )}
      </svg>

      {/* Custom tooltip */}
      {hover && (
        <div
          className="absolute pointer-events-none bg-popover text-popover-foreground border border-border rounded px-2 py-1 text-xs shadow-md z-10"
          style={{
            left: `${(hover.x / width) * 100}%`,
            top: `${(hover.y / height) * 100}%`,
            transform: 'translate(-50%, -120%)',
            whiteSpace: 'nowrap',
          }}
        >
          <span className="font-mono font-semibold">{hover.score}</span>
          <span className="text-muted-foreground ml-2">{safeFormat(hover.date)}</span>
        </div>
      )}
    </div>
  );
}
