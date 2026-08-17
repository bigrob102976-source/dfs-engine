import { redirect } from "next/navigation";
import { NextResponse } from "next/server";

import { isAdminRole } from "./roles";
import { getCurrentUser, type CurrentUser } from "./session";

// Server Component / layout guards -- redirect on failure.

export async function requireAuth(nextPath?: string): Promise<CurrentUser> {
  const user = await getCurrentUser();
  if (!user) {
    redirect(nextPath ? `/login?next=${encodeURIComponent(nextPath)}` : "/login");
  }
  return user;
}

export async function requireAdmin(): Promise<CurrentUser> {
  const user = await requireAuth();
  if (!isAdminRole(user.role)) {
    redirect("/dashboard");
  }
  return user;
}

// API Route guards -- return a NextResponse on failure. Callers do:
//   const userOrRes = await requireAuthApi();
//   if (userOrRes instanceof NextResponse) return userOrRes;

export async function requireAuthApi(): Promise<CurrentUser | NextResponse> {
  const user = await getCurrentUser();
  if (!user) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }
  return user;
}

export async function requireAdminApi(): Promise<CurrentUser | NextResponse> {
  const userOrResponse = await requireAuthApi();
  if (userOrResponse instanceof NextResponse) return userOrResponse;
  if (!isAdminRole(userOrResponse.role)) {
    return NextResponse.json({ error: "Admin access required." }, { status: 403 });
  }
  return userOrResponse;
}
