import { requireAuth } from "@/lib/auth/guards";

import { SuccessPoller } from "./SuccessPoller";

export const dynamic = "force-dynamic";

export default async function SubscribeSuccessPage() {
  await requireAuth("/subscribe/success");
  return <SuccessPoller />;
}
