"use client";

import { useEffect, useState } from "react";

import type { NflSlateData } from "./types";

export interface UseNflDataResult {
  data: NflSlateData | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

// NFL UI M1 -- shared client-side fetch of the real NFL slate data
// endpoint. Each tab page uses this independently (simpler than a
// cross-page context store for a first UI milestone); the API route's
// own short in-memory cache keeps repeated tab navigation fast without
// needing client-side state sharing.
export function useNflData(draftGroupId: number | null): UseNflDataResult {
  const [data, setData] = useState<NflSlateData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    if (!draftGroupId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/nfl/data?draftGroupId=${draftGroupId}${refreshToken ? "&refresh=1" : ""}`)
      .then(async (res) => {
        const json = await res.json();
        if (cancelled) return;
        if (!res.ok || json.error) {
          setError(json.error || `Request failed (${res.status}).`);
          setData(null);
        } else {
          setData(json as NflSlateData);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unknown error loading NFL data.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftGroupId, refreshToken]);

  return { data, loading, error, refresh: () => setRefreshToken((t) => t + 1) };
}
