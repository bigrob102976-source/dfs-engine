"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";

import { AUTH_INPUT_CLASS, AUTH_LABEL_CLASS } from "./AuthCard";
import { DevLinkNotice } from "./DevLinkNotice";

export function SignupForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [devVerificationLink, setDevVerificationLink] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Something went wrong. Please try again.");
        setSubmitting(false);
        return;
      }
      setDevVerificationLink(body.devVerificationLink ?? null);
      router.refresh();
    } catch {
      setError("Something went wrong. Please try again.");
      setSubmitting(false);
    }
  }

  if (devVerificationLink) {
    return (
      <div>
        <p className="mb-4 text-sm text-text">Account created. You&apos;re signed in.</p>
        <DevLinkNotice label="Verify your email:" link={devVerificationLink} />
        <PrimaryButton onClick={() => router.push("/dashboard")} className="w-full py-2 text-sm">
          Continue to Dashboard
        </PrimaryButton>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <label className={AUTH_LABEL_CLASS} htmlFor="email">
        Email
      </label>
      <input
        id="email"
        type="email"
        required
        autoFocus
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className={AUTH_INPUT_CLASS}
      />
      <label className={AUTH_LABEL_CLASS} htmlFor="password">
        Password
      </label>
      <input
        id="password"
        type="password"
        required
        minLength={8}
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className={AUTH_INPUT_CLASS}
      />
      <p className="mb-4 -mt-2 text-[11px] text-text-faint">At least 8 characters.</p>
      {error && <p className="mb-4 text-xs text-red">{error}</p>}
      <PrimaryButton type="submit" disabled={submitting} className="w-full py-2 text-sm">
        {submitting ? "Creating account..." : "Create account"}
      </PrimaryButton>
      <p className="mt-4 text-center text-xs text-text-faint">
        Already have an account?{" "}
        <Link href="/login" className="text-accent hover:text-accent-hover">
          Sign in
        </Link>
      </p>
    </form>
  );
}
