/** Behind-an-interface email sending, so a real provider (SendGrid,
 * Postmark, SES, etc.) can be dropped in later by adding one new
 * implementation file and changing index.ts's single export -- nothing
 * else in the app imports a provider directly. */
export interface EmailAdapter {
  sendVerificationEmail(args: { to: string; link: string }): Promise<{ devLink: string | null }>;
  sendPasswordResetEmail(args: { to: string; link: string }): Promise<{ devLink: string | null }>;
}
