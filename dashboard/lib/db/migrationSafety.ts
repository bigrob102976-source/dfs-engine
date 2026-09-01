// M3G -- a lightweight migration safety guardrail. NOT a SQL parser --
// a small set of regex checks for the dangerous statement shapes this
// project's own migration discipline has never needed (see every
// existing migrations-postgres/*.sql file: purely CREATE TABLE/INDEX
// and ADD COLUMN, with exactly one legitimate exception documented
// below). Exists because M2 discovered Railway is configured (outside
// this repo, in its own deploy settings) to run `npm run
// db:migrate:postgres` automatically on every deploy -- see
// lib/db/executor.ts's corrected docstring -- so ANY migration merged
// to main can reach production without a separate manual apply step.
//
// The ONE known legitimate exception to "never DROP/ALTER destructively"
// is a DROP CONSTRAINT immediately paired with an ADD CONSTRAINT that
// widens the same check (migrations-postgres/0003_stripe_billing.sql
// replaces subscriptions_provider_check to allow an additional value) --
// this guardrail still flags a bare DROP CONSTRAINT as dangerous (it
// cannot verify the paired ADD CONSTRAINT is actually a widening, only
// that one exists), requiring the same explicit override marker as any
// other flagged statement. This is intentionally conservative: a false
// positive on a genuinely safe migration costs one comment line; a
// false negative on a genuinely destructive one costs data.

export interface MigrationSafetyFinding {
  pattern: string;
  matchedText: string;
}

export interface MigrationSafetyResult {
  dangerous: boolean;
  findings: MigrationSafetyFinding[];
  overridden: boolean;
  /** true only when findings exist AND no override marker was present --
   * the condition a caller should actually treat as "block this migration." */
  blocked: boolean;
}

/** Present anywhere in a migration file (a SQL comment, so it's inert
 * to every database engine) to explicitly acknowledge that this
 * migration contains a deliberate destructive/dangerous operation.
 * Never implied, never inferred -- a human must type this exact
 * string. Findings are still reported (visible in review/tooling) even
 * when this marker is present; only `blocked` becomes false. */
export const MIGRATION_SAFETY_OVERRIDE_MARKER = "MIGRATION-SAFETY: approved-destructive";

interface DangerPattern {
  name: string;
  regex: RegExp;
}

// Order doesn't matter -- every pattern is checked independently.
const DANGER_PATTERNS: DangerPattern[] = [
  { name: "DROP TABLE", regex: /\bDROP\s+TABLE\b/gi },
  { name: "DROP COLUMN", regex: /\bDROP\s+COLUMN\b/gi },
  { name: "TRUNCATE", regex: /\bTRUNCATE\b/gi },
  { name: "DELETE FROM", regex: /\bDELETE\s+FROM\b/gi },
  { name: "destructive ALTER COLUMN ... TYPE", regex: /\bALTER\s+COLUMN\b[^;]*\bTYPE\b/gi },
  { name: "DROP CONSTRAINT", regex: /\bDROP\s+CONSTRAINT\b/gi },
];

/** Strips SQL line comments (`-- ...`) before pattern-matching the
 * statement bodies, so a comment merely MENTIONING a dangerous keyword
 * (as this very file's own docstring does) is never itself flagged.
 * The override marker is checked against the ORIGINAL text (including
 * comments), separately -- see scanMigrationSql. */
function stripSqlComments(sql: string): string {
  return sql
    .split("\n")
    .map((line) => {
      const idx = line.indexOf("--");
      return idx === -1 ? line : line.slice(0, idx);
    })
    .join("\n");
}

/** Scans one migration file's full SQL text. Never throws -- a scan is
 * inherently best-effort (see this module's own docstring: "not a
 * complete SQL parser"). */
export function scanMigrationSql(sql: string): MigrationSafetyResult {
  const codeOnly = stripSqlComments(sql);
  const findings: MigrationSafetyFinding[] = [];

  for (const { name, regex } of DANGER_PATTERNS) {
    const matches = codeOnly.match(regex);
    if (matches) {
      for (const matchedText of matches) {
        findings.push({ pattern: name, matchedText: matchedText.trim() });
      }
    }
  }

  const overridden = sql.includes(MIGRATION_SAFETY_OVERRIDE_MARKER);
  const dangerous = findings.length > 0;

  return { dangerous, findings, overridden, blocked: dangerous && !overridden };
}

/** Convenience: scans every provided (filename, sql) pair and returns
 * only the ones that would be blocked -- used by a pre-push check or a
 * test asserting "every migration file on disk passes the guardrail." */
export function findBlockedMigrations(files: Array<{ filename: string; sql: string }>): Array<{ filename: string; result: MigrationSafetyResult }> {
  const blocked: Array<{ filename: string; result: MigrationSafetyResult }> = [];
  for (const { filename, sql } of files) {
    const result = scanMigrationSql(sql);
    if (result.blocked) {
      blocked.push({ filename, result });
    }
  }
  return blocked;
}
