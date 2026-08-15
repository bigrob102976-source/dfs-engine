// Hand-rolled inline SVG mini line chart -- no charting library, mirrors
// the discipline of components/SimpleBarChart.tsx. Deliberately tiny
// (no axes, no labels): a single glanceable shape per table row/card.

export function VegasSparkline({
  points,
  width = 72,
  height = 24,
  color = "var(--accent)",
}: {
  points: number[];
  width?: number;
  height?: number;
  color?: string;
}) {
  const valid = points.filter((v) => typeof v === "number" && !Number.isNaN(v));

  if (valid.length < 2) {
    return (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="No line movement data">
        <line x1={4} y1={height / 2} x2={width - 4} y2={height / 2} stroke="var(--text-faint)" strokeWidth={1.5} strokeDasharray="2 3" />
      </svg>
    );
  }

  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const range = max - min || 1;
  const padX = 4;
  const padY = 4;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const coords = valid.map((v, i) => {
    const x = padX + (valid.length === 1 ? innerW / 2 : (i / (valid.length - 1)) * innerW);
    const y = padY + innerH - ((v - min) / range) * innerH;
    return { x, y };
  });

  const path = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(" ");
  const last = coords[coords.length - 1];
  const first = valid[0];
  const trendColor = valid[valid.length - 1] > first ? "var(--green)" : valid[valid.length - 1] < first ? "var(--red)" : color;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Line movement from ${first} to ${valid[valid.length - 1]}`}>
      <path d={path} fill="none" stroke={trendColor} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last.x} cy={last.y} r={2} fill={trendColor} />
    </svg>
  );
}
