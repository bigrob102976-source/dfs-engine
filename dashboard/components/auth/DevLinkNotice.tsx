/** Shown wherever a DEV-only email link (verification/reset) is
 * surfaced directly in the UI instead of actually being emailed -- see
 * lib/email/devEmailAdapter.ts. Never rendered once a real EmailAdapter
 * replaces the dev one. */
export function DevLinkNotice({ label, link }: { label: string; link: string }) {
  return (
    <div className="mb-4 rounded border border-yellow bg-bg-panel-raised p-3 text-xs">
      <div className="mb-1 font-semibold uppercase tracking-wide text-yellow">DEV MODE -- no email was sent</div>
      <p className="mb-2 text-text-faint">{label}</p>
      <a href={link} className="break-all text-accent hover:text-accent-hover">
        {link}
      </a>
    </div>
  );
}
