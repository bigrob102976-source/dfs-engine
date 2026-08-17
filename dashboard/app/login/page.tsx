import { AuthCard } from "@/components/auth/AuthCard";
import { LoginForm } from "@/components/auth/LoginForm";
import { sanitizeNextPath } from "@/lib/auth/safeRedirect";

export default async function LoginPage(props: PageProps<"/login">) {
  const params = await props.searchParams;
  const next = sanitizeNextPath(typeof params.next === "string" ? params.next : undefined);

  return (
    <AuthCard>
      <LoginForm next={next} />
    </AuthCard>
  );
}
