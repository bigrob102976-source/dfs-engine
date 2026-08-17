import type { EmailAdapter } from "./types";

/**
 * DEV-ONLY email adapter -- NOT a real email integration.
 *
 * No SMTP/email provider (SendGrid, Postmark, SES, etc.) is configured
 * anywhere in this project. Rather than fake a live send or invent
 * credentials, this adapter never contacts any external service: it
 * logs the link server-side and returns it directly to the caller,
 * which surfaces it in the API response / on-screen for local testing
 * (clearly labeled "DEV MODE -- no email was sent" wherever it's shown).
 *
 * Connecting a real provider is a deferred, future-milestone item --
 * swap the single export in lib/email/index.ts for a real
 * implementation of EmailAdapter; nothing else in the app needs to change.
 */
export class DevEmailAdapter implements EmailAdapter {
  async sendVerificationEmail(args: { to: string; link: string }): Promise<{ devLink: string | null }> {
    console.info(`[dev-email] Verification link for ${args.to}: ${args.link}`);
    return { devLink: args.link };
  }

  async sendPasswordResetEmail(args: { to: string; link: string }): Promise<{ devLink: string | null }> {
    console.info(`[dev-email] Password reset link for ${args.to}: ${args.link}`);
    return { devLink: args.link };
  }
}
