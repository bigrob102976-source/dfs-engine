import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";

import { __resetExecutorForTests } from "@/lib/db/executor";
import { listSportsForNav } from "../sportsVisibility";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("listSportsForNav", () => {
  it("MLB is LIVE and the other three are COMING_SOON", async () => {
    const sports = await listSportsForNav();
    const byCode = Object.fromEntries(sports.map((s) => [s.code, s.status]));
    expect(byCode.MLB).toBe("LIVE");
    expect(byCode.NFL).toBe("COMING_SOON");
    expect(byCode.NBA).toBe("COMING_SOON");
    expect(byCode.NHL).toBe("COMING_SOON");
  });

  it("returns sports ordered by sort_order (MLB first)", async () => {
    const sports = await listSportsForNav();
    expect(sports[0].code).toBe("MLB");
  });
});
