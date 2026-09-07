"use client";

import { Suspense, type ReactNode } from "react";

import { PageHeader } from "@/components/ui";
import { NflSlateSelector } from "./NflSlateSelector";
import { NflTabs } from "./NflTabs";

/** NFL UI M1 -- shared shell every NFL tab page renders: tab bar, page
 * title, and the real slate selector, wrapped in the Suspense boundary
 * Next.js requires around useSearchParams(). Keeps each individual tab
 * page focused on its own content instead of repeating this chrome. */
export function NflPageShell({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <Suspense fallback={null}>
      <NflTabs />
      <PageHeader title={title} description={description} actions={<NflSlateSelector />} />
      {children}
    </Suspense>
  );
}
