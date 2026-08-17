import { AuthCard } from "@/components/auth/AuthCard";
import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";

export default async function ResetPasswordPage(props: PageProps<"/reset-password">) {
  const params = await props.searchParams;
  const token = typeof params.token === "string" ? params.token : null;

  return (
    <AuthCard>
      <ResetPasswordForm token={token} />
    </AuthCard>
  );
}
