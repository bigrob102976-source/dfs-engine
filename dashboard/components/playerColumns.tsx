"use client";

// Column configs embed render functions (JSX closures), which cannot be
// serialized across the Server -> Client Component boundary. So instead
// of a Server Component page building a `columns` array and passing it
// as a prop, PlayerTable picks one of these pre-built, client-only
// column sets itself based on a plain `variant` string prop (which IS
// serializable). Pages only ever pass `variant="pitcher" | "hitter"`.

import type { PlayerRow } from "@/lib/types";

export interface PlayerColumn {
  key: string;
  label: string;
  sortKey?: keyof PlayerRow;
  align?: "right" | "left";
  render?: (row: PlayerRow) => React.ReactNode;
}

function fmt(value: number | null, digits = 1): string {
  return value === null || value === undefined ? "--" : value.toFixed(digits);
}

export function numericColumn(key: keyof PlayerRow, label: string, digits = 1): PlayerColumn {
  return {
    key,
    label,
    sortKey: key,
    align: "right",
    render: (row) => fmt(row[key] as number | null, digits),
  };
}

function TagList({ tags }: { tags: string[] }) {
  return (
    <span className="flex flex-wrap gap-1">
      {tags.slice(0, 3).map((t) => (
        <span key={t} className="rounded bg-bg-panel-raised px-1 text-[10px] text-text-muted">
          {t}
        </span>
      ))}
    </span>
  );
}

const REASON_COLUMN: PlayerColumn = {
  key: "reasons",
  label: "Reasons",
  render: (row) => <span className="block max-w-xs truncate text-text-muted">{row.reasons[0] ?? "--"}</span>,
};

const TAGS_COLUMN: PlayerColumn = {
  key: "tags",
  label: "Tags",
  render: (row) => <TagList tags={row.tags} />,
};

export const PITCHER_COLUMNS: PlayerColumn[] = [
  {
    key: "name",
    label: "Pitcher",
    sortKey: "name",
    render: (row) => (
      <span>
        <span className="text-text">{row.name}</span>{" "}
        <span className="text-text-faint">
          {row.team} vs {row.opponent}
        </span>
      </span>
    ),
  },
  numericColumn("salary", "Salary", 0),
  numericColumn("projection", "Projection"),
  numericColumn("ceiling", "Ceiling"),
  numericColumn("overall", "Overall"),
  numericColumn("risk", "Risk"),
  numericColumn("confidence", "Confidence"),
  numericColumn("ownership", "Ownership"),
  numericColumn("leverage", "Leverage"),
  TAGS_COLUMN,
  REASON_COLUMN,
];

// Milestone 32.3B: Big Money ML -- independent SHADOW comparison
// column, hitters only. Never sorted into overall/power/matchup/risk/
// confidence/ownership/leverage; comparison-only, same as
// ProjectionLabTable's mlProjection column. Shows "SHADOW" as the
// unit label since this is never an optimizer-selectable projection
// source (see lib/optimizerWorkspace/types.ts's ProjectionSource).
const ML_COLUMN: PlayerColumn = {
  key: "mlProjection",
  label: "Big Money ML",
  sortKey: "mlProjection",
  align: "right",
  render: (row) => (row.mlProjection === null ? "--" : row.mlProjection.toFixed(1)),
};

export const HITTER_COLUMNS: PlayerColumn[] = [
  { key: "name", label: "Player", sortKey: "name", render: (row) => row.name },
  { key: "team", label: "Team", sortKey: "team", render: (row) => row.team },
  { key: "battingOrder", label: "Order", sortKey: "battingOrder", align: "right", render: (row) => row.battingOrder ?? "--" },
  numericColumn("salary", "Salary", 0),
  numericColumn("projection", "Projection"),
  ML_COLUMN,
  numericColumn("power", "Power"),
  numericColumn("matchup", "Matchup"),
  numericColumn("risk", "Risk"),
  numericColumn("confidence", "Confidence"),
  numericColumn("ownership", "Ownership"),
  numericColumn("leverage", "Leverage"),
  TAGS_COLUMN,
  REASON_COLUMN,
];
