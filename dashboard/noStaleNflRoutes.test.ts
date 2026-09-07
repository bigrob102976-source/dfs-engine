import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/** NFL public access -- regression guard for the exact bug that caused
 * a live 404: app/nfl/optimizer/page.tsx's own router.push() calls
 * still pointed at /dashboard/nfl/lineups and /dashboard/nfl/players,
 * both deleted when NFL moved to /nfl. A per-file test wouldn't have
 * caught a SIMILAR stale reference in some other NFL file, so this
 * scans every real source file under app/nfl and components/nfl for
 * the literal old path -- the whole prefix is gone, so no real
 * reference to it should ever exist there again. */

const ROOTS = ["app/nfl", "components/nfl"];
const SOURCE_EXTENSIONS = [".ts", ".tsx"];
const SKIP_DIR_NAMES = new Set(["__tests__", "node_modules"]);

function collectSourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (SKIP_DIR_NAMES.has(entry)) continue;
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      out.push(...collectSourceFiles(full));
    } else if (SOURCE_EXTENSIONS.some((ext) => entry.endsWith(ext))) {
      out.push(full);
    }
  }
  return out;
}

describe("no stale /dashboard/nfl references", () => {
  it("no NFL source file under app/nfl or components/nfl references the deleted /dashboard/nfl path", () => {
    const offenders: string[] = [];
    for (const root of ROOTS) {
      for (const file of collectSourceFiles(root)) {
        const content = readFileSync(file, "utf-8");
        if (content.includes("/dashboard/nfl")) {
          offenders.push(file);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
