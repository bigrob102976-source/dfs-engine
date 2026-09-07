import { describe, expect, it } from "vitest";

import NflLayout from "../layout";

/** NFL public access -- this layout must NEVER redirect, for anyone.
 * Unlike the prior admin-only/member-only versions, it has no
 * auth/session/DB dependency at all, so this test needs none either. */
describe("NFL workspace layout access", () => {
  it("renders children for a completely anonymous visitor -- never redirects", () => {
    const result = NflLayout({ children: "content" as unknown as React.ReactNode });
    expect(result).toBeTruthy();
  });
});
