"use client";

// Hand-rolled SVG bar chart -- deliberately no charting library dependency
// for what is a handful of small time-series bars per page.

export interface ChartPoint {
  label: string;
  value: number | null;
}

export function SimpleBarChart({ title, points, color = "var(--accent)", digits = 2 }: {
  title: string;
  points: ChartPoint[];
  color?: string;
  digits?: number;
}) {
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  const max = values.length ? Math.max(...values, 0) : 1;
  const width = Math.max(points.length * 48, 200);
  const height = 140;
  const barWidth = 28;

  return (
    <div className="rounded-lg border border-border bg-bg-panel p-4">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-faint">{title}</div>
      {values.length === 0 ? (
        <div className="py-8 text-center text-xs text-text-faint">No data yet.</div>
      ) : (
        <svg width="100%" height={height + 24} viewBox={`0 0 ${width} ${height + 24}`}>
          {points.map((p, i) => {
            const x = i * 48 + 10;
            const h = p.value !== null ? (p.value / max) * height : 0;
            return (
              <g key={p.label}>
                <rect x={x} y={height - h} width={barWidth} height={h} fill={p.value !== null ? color : "transparent"} rx={2} />
                <text x={x + barWidth / 2} y={height - h - 4} textAnchor="middle" fontSize="9" fill="var(--text-muted)">
                  {p.value !== null ? p.value.toFixed(digits) : ""}
                </text>
                <text x={x + barWidth / 2} y={height + 14} textAnchor="middle" fontSize="9" fill="var(--text-faint)">
                  {p.label.slice(5)}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
