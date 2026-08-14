import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { PrimaryButton } from "@/components/ui/Button";

const SESSION_COOKIE = "dfs_dashboard_session";

async function login(formData: FormData) {
  "use server";
  const password = String(formData.get("password") ?? "");
  const next = String(formData.get("next") ?? "/dashboard");
  const expected = process.env.DASHBOARD_PASSWORD;

  if (!expected || password !== expected) {
    redirect(`/login?error=1&next=${encodeURIComponent(next)}`);
  }

  const store = await cookies();
  store.set(SESSION_COOKIE, password, {
    httpOnly: true,
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 7,
  });
  redirect(next);
}

export default async function LoginPage(props: PageProps<"/login">) {
  const params = await props.searchParams;
  const next = typeof params.next === "string" ? params.next : "/dashboard";
  const hasError = params.error === "1";

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <form action={login} className="w-full max-w-sm rounded-2xl border border-border bg-bg-panel p-8 shadow-[var(--shadow-card)]">
        <div className="mb-6">
          <h1 className="text-lg font-semibold tracking-tight text-text">
            BIG MONEY <span className="text-gold">DFS</span>
          </h1>
          <p className="text-[11px] uppercase tracking-widest text-text-faint">AI Research Terminal</p>
        </div>
        <input type="hidden" name="next" value={next} />
        <label className="mb-1 block text-xs text-text-muted" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoFocus
          className="mb-4 w-full rounded border border-border bg-bg-panel-raised px-3 py-2 text-sm text-text outline-none focus:border-accent"
        />
        {hasError && <p className="mb-4 text-xs text-red">Incorrect password.</p>}
        <PrimaryButton type="submit" className="w-full py-2 text-sm">
          Sign in
        </PrimaryButton>
      </form>
    </div>
  );
}
