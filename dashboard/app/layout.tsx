import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { ThemeProvider, THEME_INIT_SCRIPT } from "@/components/theme/ThemeProvider";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "BIG MONEY DFS — AI Research Terminal",
  description: "AI-driven MLB DFS research, projections, and lineup optimization.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        {/* Applies data-theme before first paint -- no flash of the wrong
            theme. Mirrors ThemeProvider's own resolution logic exactly. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
