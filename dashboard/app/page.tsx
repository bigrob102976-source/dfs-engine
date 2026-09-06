import { redirect } from "next/navigation";

// NFL public access: this branch (nfl-dev) serves ONLY the isolated
// nfl-web Railway service, so its root landing page is the NFL product
// itself, reachable with no login (see proxy.ts's exact "/" match and
// app/nfl/layout.tsx). This file is branch-isolated from MLB's own
// deployment (dfs-engine builds from main, which still redirects "/" to
// /dashboard) -- changing it here has no effect on MLB.
export default function Home() {
  redirect("/nfl");
}
