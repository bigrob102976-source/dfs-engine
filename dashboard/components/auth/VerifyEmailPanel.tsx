"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Status = "verifying" | "success" | "error";

export function VerifyEmailPanel({ token }: { token: string | null }) {
  const [status, setStatus] = useState<Status>(token ? "verifying" : "error");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    fetch("/api/auth/verify-email", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then(async (res) => {
        if (cancelled) return;
        const body = await res.json();
        if (res.ok) {
          setStatus("success");
        } else {
          setStatus("error");
          setMessage(body.error ?? "This verification link is invalid or has expired.");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("error");
          setMessage("Something went wrong. Please try again.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (status === "verifying") {
    return <p className="text-sm text-text-faint">Verifying your email...</p>;
  }

  if (status === "success") {
    return (
      <div>
        <p className="mb-4 text-sm text-green">Your email has been verified.</p>
        <Link href="/dashboard" className="text-xs text-accent hover:text-accent-hover">
          Continue to Dashboard →
        </Link>
      </div>
    );
  }

  return (
    <div>
      <p className="mb-4 text-sm text-red">{message ?? "This verification link is invalid or has expired."}</p>
      <Link href="/dashboard" className="text-xs text-accent hover:text-accent-hover">
        Continue to Dashboard →
      </Link>
    </div>
  );
}
