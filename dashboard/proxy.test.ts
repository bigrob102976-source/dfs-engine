import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { proxy } from "./proxy";

const SESSION_COOKIE = "bigmoney_session";

function requestFor(pathname: string, cookieValue?: string): NextRequest {
  const req = new NextRequest(new URL(pathname, "http://localhost:3000"));
  if (cookieValue) {
    req.cookies.set(SESSION_COOKIE, cookieValue);
  }
  return req;
}

describe("proxy (cheap Edge session-cookie gate)", () => {
  it("redirects a cookie-less request to a protected dashboard path to /login with ?next=", () => {
    const res = proxy(requestFor("/dashboard/optimizer"));
    expect(res.status).toBe(307);
    const location = new URL(res.headers.get("location")!);
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/dashboard/optimizer");
  });

  it("redirects a cookie-less request to a protected admin path", () => {
    const res = proxy(requestFor("/admin"));
    expect(res.status).toBe(307);
    expect(new URL(res.headers.get("location")!).pathname).toBe("/login");
  });

  it("redirects a cookie-less request to a protected admin API route", () => {
    const res = proxy(requestFor("/api/admin/users"));
    expect(res.status).toBe(307);
  });

  it("passes through when a session cookie is present, regardless of validity (deep check happens server-side)", () => {
    const res = proxy(requestFor("/dashboard", "any-cookie-value"));
    expect(res.status).toBe(200); // NextResponse.next()
  });

  it("never redirects public auth pages, even without a cookie", () => {
    for (const path of ["/login", "/signup", "/forgot-password", "/reset-password", "/verify-email"]) {
      const res = proxy(requestFor(path));
      expect(res.status).toBe(200);
    }
  });

  it("never redirects the auth API routes, even without a cookie", () => {
    for (const path of ["/api/auth/login", "/api/auth/signup", "/api/auth/logout"]) {
      const res = proxy(requestFor(path));
      expect(res.status).toBe(200);
    }
  });

  it("never redirects the public /pricing page, even without a cookie", () => {
    const res = proxy(requestFor("/pricing"));
    expect(res.status).toBe(200);
  });

  it("never redirects the Stripe webhook route, even without a cookie (it carries none -- signature verification is its own auth)", () => {
    const res = proxy(requestFor("/api/billing/stripe/webhook"));
    expect(res.status).toBe(200);
  });

  it("still redirects a cookie-less request to /subscribe (checkout requires a real account, unlike /pricing)", () => {
    const res = proxy(requestFor("/subscribe"));
    expect(res.status).toBe(307);
    const location = new URL(res.headers.get("location")!);
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/subscribe");
  });

  it("never redirects GET /api/health, even without a cookie -- a load balancer sends none", () => {
    const res = proxy(requestFor("/api/health"));
    expect(res.status).toBe(200); // NextResponse.next() -- reaches the route handler, no /login redirect
  });

  it("still redirects a cookie-less request to a genuinely protected member API route", () => {
    const res = proxy(requestFor("/api/account"));
    expect(res.status).toBe(307);
    expect(new URL(res.headers.get("location")!).pathname).toBe("/login");
  });

  it("still redirects a cookie-less request to /admin/slates specifically (not just /admin generically)", () => {
    const res = proxy(requestFor("/admin/slates"));
    expect(res.status).toBe(307);
    expect(new URL(res.headers.get("location")!).pathname).toBe("/login");
  });

  describe("NFL local dev auto-login intercept", () => {
    afterEach(() => {
      vi.unstubAllEnvs();
    });

    it("dev+flag=true, cookie-less /dashboard/nfl request: redirects to /api/dev/auto-login with next=", () => {
      vi.stubEnv("NODE_ENV", "development");
      vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");

      const res = proxy(requestFor("/dashboard/nfl/players"));
      expect(res.status).toBe(307);
      const location = new URL(res.headers.get("location")!);
      expect(location.pathname).toBe("/api/dev/auto-login");
      expect(location.searchParams.get("next")).toBe("/dashboard/nfl/players");
    });

    it("dev+flag=true, session cookie already present: passes through untouched, no auto-login redirect", () => {
      vi.stubEnv("NODE_ENV", "development");
      vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");

      const res = proxy(requestFor("/dashboard/nfl", "any-cookie-value"));
      expect(res.status).toBe(200);
    });

    it("dev+flag=false: falls through to the normal /login redirect", () => {
      vi.stubEnv("NODE_ENV", "development");
      vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "false");

      const res = proxy(requestFor("/dashboard/nfl"));
      expect(new URL(res.headers.get("location")!).pathname).toBe("/login");
    });

    it("production+flag=true: falls through to the normal /login redirect -- production is never intercepted", () => {
      vi.stubEnv("NODE_ENV", "production");
      vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");

      const res = proxy(requestFor("/dashboard/nfl"));
      expect(new URL(res.headers.get("location")!).pathname).toBe("/login");
    });

    it("dev+flag=true, but a non-NFL dashboard path: still falls through to /login, unaffected", () => {
      vi.stubEnv("NODE_ENV", "development");
      vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");

      const res = proxy(requestFor("/dashboard/optimizer"));
      expect(new URL(res.headers.get("location")!).pathname).toBe("/login");
    });

    it("never redirects /api/dev/auto-login itself, even without a cookie -- it must be reachable to establish the first session", () => {
      const res = proxy(requestFor("/api/dev/auto-login"));
      expect(res.status).toBe(200);
    });
  });
});
