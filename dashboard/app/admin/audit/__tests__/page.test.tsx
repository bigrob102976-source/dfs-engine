import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { recordAuditLog } = await import("@/lib/db/auditLog");

const AdminAuditPage = (await import("../page")).default;

function props(search: Record<string, string> = {}) {
  return { params: Promise.resolve({}), searchParams: Promise.resolve(search) };
}

beforeEach(() => {
  __resetDbForTests();
});

describe("AdminAuditPage", () => {
  it("shows an empty state when no entries exist", async () => {
    render(await AdminAuditPage(props()));
    expect(screen.getByText("No audit entries match this search.")).toBeInTheDocument();
  });

  it("renders a real audit entry with a Success result (append-only, only successful mutations are ever logged)", async () => {
    recordAuditLog({ actorUserId: null, actorLabel: "system", action: "admin_bootstrap", targetType: "user", targetId: "u1" });

    render(await AdminAuditPage(props()));
    expect(screen.getByText("admin_bootstrap")).toBeInTheDocument();
    expect(screen.getByText("system")).toBeInTheDocument();
    expect(screen.getByText("Success")).toBeInTheDocument();
    expect(screen.getByText("user:u1")).toBeInTheDocument();
  });
});
