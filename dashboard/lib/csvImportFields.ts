/** Mirror of external_projections/csv_import/column_detection.py's
 * CANONICAL_FIELDS -- drives the Manual Mapping panel's field list and
 * labels. `name` and `projection` are the two fields a row must have to
 * be importable at all (see importer.py's "no projection, no record"
 * rule); every other field simply stays null when unmapped. */

export interface CanonicalFieldOption {
  field: string;
  label: string;
  required: boolean;
}

export const CANONICAL_FIELDS: CanonicalFieldOption[] = [
  { field: "name", label: "Player Name", required: true },
  { field: "projection", label: "Projection", required: true },
  { field: "team", label: "Team", required: false },
  { field: "opponent", label: "Opponent", required: false },
  { field: "position", label: "Position", required: false },
  { field: "salary", label: "Salary", required: false },
  { field: "ceiling", label: "Ceiling", required: false },
  { field: "floor", label: "Floor", required: false },
  { field: "ownership", label: "Ownership", required: false },
  { field: "slate", label: "Slate", required: false },
  { field: "player_id", label: "Player ID", required: false },
];
