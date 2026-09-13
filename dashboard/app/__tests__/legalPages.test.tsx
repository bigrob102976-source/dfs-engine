import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PrivacyPage from "../privacy/page";
import ResponsiblePlayPage from "../responsible-play/page";
import SupportPage from "../support/page";
import TermsPage from "../terms/page";

// Launch Blocker Sprint 1 (2026-09-13): these pages did not exist at all
// before this sprint -- a real-money DFS product with zero Terms of
// Service, Privacy Policy, responsible-play messaging, or support page
// was a P0 launch blocker. Smoke-tests that each renders without
// throwing and carries the content the sprint required.
describe("legal/trust pages render without crashing", () => {
  it("/terms renders and covers the required disclosures", () => {
    render(<TermsPage />);
    expect(screen.getByRole("heading", { name: "Terms of Service" })).toBeInTheDocument();
    expect(screen.getByText(/not a guarantee/i)).toBeInTheDocument();
    expect(screen.getByText(/not legal advice/i)).toBeInTheDocument();
  });

  it("/privacy renders and reflects only what the app actually does", () => {
    render(<PrivacyPage />);
    expect(screen.getByRole("heading", { name: "Privacy Policy" })).toBeInTheDocument();
    expect(screen.getByText(/no self-service/i)).toBeInTheDocument();
    expect(screen.getByText(/do not use any third-party analytics/i)).toBeInTheDocument();
  });

  it("/responsible-play renders and flags the resource list for legal review", () => {
    render(<ResponsiblePlayPage />);
    expect(screen.getByRole("heading", { name: "Responsible Play" })).toBeInTheDocument();
    expect(screen.getByText(/cannot afford to lose/i)).toBeInTheDocument();
    expect(screen.getByText(/needs jurisdiction-specific legal\/compliance review/i)).toBeInTheDocument();
  });

  it("/support renders and honestly flags no support address is configured", () => {
    render(<SupportPage />);
    expect(screen.getByRole("heading", { name: "Support" })).toBeInTheDocument();
    expect(screen.getByText(/support address not yet configured/i)).toBeInTheDocument();
  });
});
