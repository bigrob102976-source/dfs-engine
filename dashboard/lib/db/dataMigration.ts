// Milestone 30: LOCAL admin/developer data migration tool -- copies every
// row from the local SQLite database into a configured PostgreSQL
// database for a one-time production cutover. This module is pure
// orchestration logic (table order, redaction, fail-closed safety
// checks) decoupled from both real database drivers via the
// MigrationSource/MigrationTarget interfaces below, so it can be fully
// unit-tested without a real SQLite file or a real Postgres server --
// see __tests__/dataMigration.test.ts. The CLI wrapper that wires this to
// lib/db/client.ts (SQLite) and lib/db/postgresClient.ts (Postgres) lives
// in scripts/migrate-sqlite-to-postgres.ts.
//
// SAFETY MODEL:
//  - Dry run (buildDryRunReport) never touches the target at all -- it
//    only reads from SQLite and returns counts + one REDACTED sample row
//    per table, so an operator can sanity-check shape/volume before
//    trusting the tool with a real database.
//  - The real run (runDataMigration) refuses to write into any target
//    table that already has rows (SKIPPED_ALREADY_MIGRATED) -- this tool
//    is for a one-time initial cutover, never a silent merge that could
//    duplicate or clobber rows already live in production.
//  - After inserting each table, the target's row count is re-checked
//    against the source count; any mismatch throws immediately and stops
//    the whole run rather than continuing on to later tables with
//    unverified data.
//  - Nothing here ever prints or logs a real password hash, session/
//    verification/reset token hash, or Stripe customer id -- see
//    SENSITIVE COLUMNS below and redactRow().

export interface TableMigrationSpec {
  name: string;
  /** Full column list, in insert order. */
  columns: string[];
  primaryKeyColumn: string;
  /** Columns whose real value must never appear in a printed/logged
   * report -- the migration itself still copies the real value into
   * Postgres; only report/log OUTPUT is redacted. */
  sensitiveColumns: string[];
  /** Nullable columns that reference this same table's own primary key
   * (e.g. users.beta_access_granted_by -> users.id). Migrated as NULL on
   * the initial insert, then backfilled in a second pass once every row
   * in the table exists -- so insertion order within the table never
   * matters. */
  selfReferentialColumns?: string[];
}

// Ordered so every foreign key referenced by a table has already been
// inserted by the time that table is migrated (self-referential columns
// on `users` are the one exception, handled via selfReferentialColumns).
export const MIGRATION_TABLES: TableMigrationSpec[] = [
  { name: "sports", primaryKeyColumn: "code", columns: ["code", "name", "status", "sort_order"], sensitiveColumns: [] },
  { name: "plans", primaryKeyColumn: "id", columns: ["id", "name", "price_cents", "billing_interval", "trial_days", "is_active", "created_at"], sensitiveColumns: [] },
  {
    name: "users",
    primaryKeyColumn: "id",
    columns: [
      "id", "email", "password_hash", "role", "display_name", "email_verified_at", "disabled_at",
      "stripe_customer_id", "trial_consumed_at", "created_at", "updated_at",
      "beta_access_granted_at", "beta_access_granted_by",
    ],
    sensitiveColumns: ["password_hash", "stripe_customer_id"],
    selfReferentialColumns: ["beta_access_granted_by"],
  },
  { name: "sessions", primaryKeyColumn: "id", columns: ["id", "token_hash", "user_id", "user_agent", "created_at", "expires_at"], sensitiveColumns: ["token_hash"] },
  { name: "email_verification_tokens", primaryKeyColumn: "id", columns: ["id", "user_id", "token_hash", "expires_at", "consumed_at", "created_at"], sensitiveColumns: ["token_hash"] },
  { name: "password_reset_tokens", primaryKeyColumn: "id", columns: ["id", "user_id", "token_hash", "expires_at", "consumed_at", "created_at"], sensitiveColumns: ["token_hash"] },
  {
    name: "subscriptions",
    primaryKeyColumn: "id",
    columns: [
      "id", "user_id", "plan_id", "status", "provider", "provider_subscription_id", "provider_price_id",
      "trial_ends_at", "current_period_start", "current_period_end", "cancel_at_period_end",
      "last_stripe_event_at", "canceled_at", "created_at", "updated_at",
    ],
    sensitiveColumns: [],
  },
  { name: "entitlements", primaryKeyColumn: "key", columns: ["key", "sport_code", "label"], sensitiveColumns: [] },
  { name: "user_entitlements", primaryKeyColumn: "id", columns: ["id", "user_id", "entitlement_key", "granted_by", "reason", "created_at", "expires_at"], sensitiveColumns: [] },
  { name: "feature_flags", primaryKeyColumn: "key", columns: ["key", "sport_code", "label", "state", "updated_at", "updated_by"], sensitiveColumns: [] },
  { name: "usage_events", primaryKeyColumn: "id", columns: ["id", "user_id", "event_type", "metadata_json", "created_at"], sensitiveColumns: [] },
  { name: "admin_audit_log", primaryKeyColumn: "id", columns: ["id", "actor_user_id", "actor_label", "action", "target_type", "target_id", "metadata_json", "created_at"], sensitiveColumns: [] },
  { name: "stripe_webhook_events", primaryKeyColumn: "id", columns: ["id", "type", "status", "error", "received_at", "processed_at"], sensitiveColumns: [] },
  {
    name: "slate_status",
    primaryKeyColumn: "id",
    columns: [
      "id", "slate_date", "slate_id", "slate_label", "status",
      "pool_path", "match_report_path", "ownership_path", "native_snapshot_path", "ai_snapshot_path",
      "vegas_snapshot_path", "research_snapshot_path", "source_hash", "source_provenance", "validation_json",
      "last_processed_at", "last_refreshed_at",
      "published_version", "published_at", "published_by", "published_pool_path", "published_match_report_path",
      "published_ownership_path", "published_native_snapshot_path", "published_ai_snapshot_path",
      "published_vegas_snapshot_path", "published_research_snapshot_path", "published_source_hash",
      "created_at", "updated_at",
    ],
    sensitiveColumns: [],
  },
  {
    name: "slate_publish_history",
    primaryKeyColumn: "id",
    columns: [
      "id", "slate_date", "slate_id", "slate_label", "data_version", "event", "published_at", "published_by",
      "source_hash", "pool_path", "match_report_path", "ownership_path", "native_snapshot_path",
      "ai_snapshot_path", "vegas_snapshot_path", "research_snapshot_path",
    ],
    sensitiveColumns: [],
  },
  {
    name: "jobs",
    primaryKeyColumn: "id",
    columns: [
      "id", "job_type", "slate_date", "slate_id", "status", "created_by", "created_at", "started_at",
      "finished_at", "updated_at", "progress", "current_step", "error_code", "safe_error_message",
      "worker_id", "attempt_count", "max_attempts", "payload_json",
    ],
    sensitiveColumns: [],
  },
  { name: "worker_heartbeats", primaryKeyColumn: "worker_id", columns: ["worker_id", "last_seen_at", "status", "metadata_json"], sensitiveColumns: [] },
];

export type MigrationRow = Record<string, unknown>;

/** Read-only access to the local SQLite database -- implemented against
 * a real `DatabaseSync` in the CLI wrapper, and against an in-memory
 * fixture in tests. Deliberately synchronous, matching node:sqlite. */
export interface MigrationSource {
  countRows(table: string): number;
  readRows(table: string): MigrationRow[];
}

/** Write access to the target PostgreSQL database -- implemented against
 * a real `pg.Pool`/`PostgresQueryable` in the CLI wrapper, and against an
 * in-memory fixture in tests (see this milestone's "no real cloud
 * resources required in unit tests" instruction). */
export interface MigrationTarget {
  countRows(table: string): Promise<number>;
  insertRows(table: string, columns: string[], rows: MigrationRow[]): Promise<void>;
  /** Backfills one self-referential FK column, row by row, after every
   * row in the table already exists. */
  updateSelfReferentialColumn(table: string, primaryKeyColumn: string, column: string, rows: MigrationRow[]): Promise<void>;
}

/** Returns a shallow copy of `row` with every sensitive column masked --
 * for report/log OUTPUT only. Never used on the path that actually writes
 * to Postgres (runDataMigration passes the real, unredacted row to
 * MigrationTarget.insertRows). */
export function redactRow(spec: TableMigrationSpec, row: MigrationRow): MigrationRow {
  const redacted: MigrationRow = { ...row };
  for (const column of spec.sensitiveColumns) {
    if (column in redacted && redacted[column] != null) {
      redacted[column] = "[REDACTED]";
    }
  }
  return redacted;
}

export interface TableDryRunEntry {
  table: string;
  sourceRowCount: number;
  /** One row, redacted, purely so an operator can eyeball the shape of
   * the data about to be migrated -- null when the table is empty. */
  sampleRedactedRow: MigrationRow | null;
}

/** Read-only preview: counts every table and returns one redacted sample
 * row each, without ever connecting to or writing into the target
 * database. Safe to run against a real production-bound SQLite file at
 * any time. */
export function buildDryRunReport(source: MigrationSource): TableDryRunEntry[] {
  return MIGRATION_TABLES.map((spec) => {
    const sourceRowCount = source.countRows(spec.name);
    if (sourceRowCount === 0) {
      return { table: spec.name, sourceRowCount, sampleRedactedRow: null };
    }
    const [firstRow] = source.readRows(spec.name);
    return { table: spec.name, sourceRowCount, sampleRedactedRow: firstRow ? redactRow(spec, firstRow) : null };
  });
}

export type TableMigrationStatus = "MIGRATED" | "SKIPPED_EMPTY_SOURCE" | "SKIPPED_ALREADY_MIGRATED";

export interface TableMigrationResult {
  table: string;
  status: TableMigrationStatus;
  sourceRowCount: number;
  targetRowCountBefore: number;
  rowsInserted: number;
  targetRowCountAfter: number;
}

export class DataMigrationError extends Error {}

/** Copies every MIGRATION_TABLES table from `source` into `target`, in
 * dependency order, stopping immediately (throwing DataMigrationError) on
 * any insert failure or post-insert row-count mismatch -- never
 * continuing on to later tables with unverified data in an earlier one. */
export async function runDataMigration(source: MigrationSource, target: MigrationTarget): Promise<TableMigrationResult[]> {
  const results: TableMigrationResult[] = [];

  for (const spec of MIGRATION_TABLES) {
    const sourceRowCount = source.countRows(spec.name);
    const targetRowCountBefore = await target.countRows(spec.name);

    if (sourceRowCount === 0) {
      results.push({ table: spec.name, status: "SKIPPED_EMPTY_SOURCE", sourceRowCount, targetRowCountBefore, rowsInserted: 0, targetRowCountAfter: targetRowCountBefore });
      continue;
    }

    if (targetRowCountBefore > 0) {
      results.push({ table: spec.name, status: "SKIPPED_ALREADY_MIGRATED", sourceRowCount, targetRowCountBefore, rowsInserted: 0, targetRowCountAfter: targetRowCountBefore });
      continue;
    }

    const rows = source.readRows(spec.name);
    const selfRefColumns = spec.selfReferentialColumns ?? [];
    const insertColumns = spec.columns.filter((c) => !selfRefColumns.includes(c));

    try {
      await target.insertRows(spec.name, insertColumns, rows);
      for (const column of selfRefColumns) {
        await target.updateSelfReferentialColumn(spec.name, spec.primaryKeyColumn, column, rows);
      }
    } catch (err) {
      throw new DataMigrationError(
        `Migrating table "${spec.name}" failed -- stopping here rather than continuing on to later tables. ` +
        `Tables already migrated in this run are unaffected; re-run after fixing the cause (already-migrated ` +
        `tables will be safely skipped). Underlying error: ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    const targetRowCountAfter = await target.countRows(spec.name);
    if (targetRowCountAfter !== sourceRowCount) {
      throw new DataMigrationError(
        `Row count mismatch after migrating "${spec.name}": source had ${sourceRowCount} row(s), target has ` +
        `${targetRowCountAfter} row(s) after insert. Stopping -- do not proceed to later tables with unverified data.`,
      );
    }

    results.push({ table: spec.name, status: "MIGRATED", sourceRowCount, targetRowCountBefore, rowsInserted: rows.length, targetRowCountAfter });
  }

  return results;
}
