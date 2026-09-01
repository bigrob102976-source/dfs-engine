import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { findBlockedMigrations } from "../migrationSafety";
import { listPostgresMigrationFiles } from "../postgresClient";

// M3F/M3G: real gate over every migration file THIS repository actually
// ships, going forward -- run against the real files on disk (not
// synthetic fixtures) so a future contributor who adds a genuinely
// destructive migration without the explicit override marker gets a
// real, failing test, not just a guideline. Scoped to migrations from
// 0010 onward (M1's first canonical-schema migration) -- pre-existing
// history (0001-0009) already shipped to production before this
// guardrail existed and is not retroactively judged; see
// migrationSafety.ts's own docstring for the one already-known,
// already-applied exception (0003's DROP CONSTRAINT/ADD CONSTRAINT pair).
const GATE_FROM_MIGRATION_NUMBER = 10;

function migrationNumber(filename: string): number {
  const match = filename.match(/^(\d+)_/);
  return match ? parseInt(match[1], 10) : 0;
}

describe("migration safety gate (Postgres dialect)", () => {
  it("every migration from 0010 onward passes the guardrail (additive-only, or explicitly overridden)", () => {
    const dir = path.join(process.cwd(), "lib", "db", "migrations-postgres");
    const files = listPostgresMigrationFiles()
      .filter((filename) => migrationNumber(filename) >= GATE_FROM_MIGRATION_NUMBER)
      .map((filename) => ({ filename, sql: fs.readFileSync(path.join(dir, filename), "utf-8") }));

    expect(files.length).toBeGreaterThan(0); // sanity: the gate is actually exercising real files

    const blocked = findBlockedMigrations(files);
    expect(blocked).toEqual([]);
  });
});
