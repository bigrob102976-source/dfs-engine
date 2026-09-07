"use client";

import { Suspense, type ReactNode } from "react";

import { PageHeader } from "@/components/ui";
import { NflSlateSelector } from "./NflSlateSelector";

/** NFL UI M1 -- shared shell every NFL page renders: page title and the
 * real slate selector, wrapped in the Suspense boundary Next.js
 * requires around useSearchParams(). Keeps each individual page
 * focused on its own content instead of repeating this chrome.
 *
 * M16D: the tab bar this used to render (NflTabs) was removed -- primary
 * NFL navigation now lives in the shared Sidebar (app/nfl/layout.tsx),
 * so a second full navigation system here would just duplicate it. */
export function NflPageShell({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <Suspense fallback={null}>
      <PageHeader title={title} description={description} actions={<NflSlateSelector />} />
      {children}
    </Suspense>
  );
}
