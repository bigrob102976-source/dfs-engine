"use client";

import { useSearchParams } from "next/navigation";

import { DEFAULT_NFL_DRAFT_GROUP_ID } from "./types";

export function useNflDraftGroupId(): number {
  const searchParams = useSearchParams();
  const raw = searchParams.get("draftGroupId");
  const parsed = raw ? Number.parseInt(raw, 10) : NaN;
  return Number.isInteger(parsed) && parsed > 0 ? parsed : DEFAULT_NFL_DRAFT_GROUP_ID;
}
