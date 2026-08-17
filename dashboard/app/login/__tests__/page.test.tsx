import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let capturedNext: string | undefined;
vi.mock("@/components/auth/LoginForm", () => ({
  LoginForm: ({ next }: { next: string }) => {
    capturedNext = next;
    return null;
  },
}));
vi.mock("@/components/auth/AuthCard", () => ({
  AuthCard: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import LoginPage from "../page";

function props(next?: string) {
  return { params: Promise.resolve({}), searchParams: Promise.resolve(next === undefined ? {} : { next }) };
}

describe("LoginPage", () => {
  it("passes through a safe internal next path unchanged", async () => {
    render(await LoginPage(props("/dashboard/optimizer")));
    expect(capturedNext).toBe("/dashboard/optimizer");
  });

  it("defaults to /dashboard when next is missing", async () => {
    render(await LoginPage(props()));
    expect(capturedNext).toBe("/dashboard");
  });

  it("sanitizes an external URL down to /dashboard (open redirect regression guard)", async () => {
    render(await LoginPage(props("https://evil.example/phish")));
    expect(capturedNext).toBe("/dashboard");
  });

  it("sanitizes a protocol-relative URL down to /dashboard", async () => {
    render(await LoginPage(props("//evil.example")));
    expect(capturedNext).toBe("/dashboard");
  });
});
