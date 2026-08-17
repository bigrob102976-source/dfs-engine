import { AuthCard } from "@/components/auth/AuthCard";
import { VerifyEmailPanel } from "@/components/auth/VerifyEmailPanel";

export default async function VerifyEmailPage(props: PageProps<"/verify-email">) {
  const params = await props.searchParams;
  const token = typeof params.token === "string" ? params.token : null;

  return (
    <AuthCard>
      <VerifyEmailPanel token={token} />
    </AuthCard>
  );
}
