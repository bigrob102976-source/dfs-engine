import { describe, expect, it } from "vitest";

import { toPostgresPlaceholders } from "../sqlExecutor";

describe("toPostgresPlaceholders", () => {
  it("rewrites a single `?` to `$1`", () => {
    expect(toPostgresPlaceholders("SELECT * FROM users WHERE id = ?")).toBe("SELECT * FROM users WHERE id = $1");
  });

  it("rewrites multiple `?` in order to $1, $2, $3, ...", () => {
    expect(toPostgresPlaceholders("INSERT INTO users (id, email, role) VALUES (?, ?, ?)")).toBe(
      "INSERT INTO users (id, email, role) VALUES ($1, $2, $3)",
    );
  });

  it("leaves SQL with no placeholders unchanged", () => {
    expect(toPostgresPlaceholders("SELECT COUNT(*) as c FROM users")).toBe("SELECT COUNT(*) as c FROM users");
  });

  it("does not rewrite a literal `?` inside a single-quoted string", () => {
    expect(toPostgresPlaceholders("SELECT * FROM x WHERE note = 'is this ok?' AND id = ?")).toBe(
      "SELECT * FROM x WHERE note = 'is this ok?' AND id = $1",
    );
  });

  it("handles a multi-line query with several placeholders", () => {
    const sql = `INSERT INTO subscriptions (\n  id, user_id, plan_id\n) VALUES (?, ?, ?)`;
    expect(toPostgresPlaceholders(sql)).toContain("VALUES ($1, $2, $3)");
  });
});
