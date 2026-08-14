import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "../ThemeProvider";
import { ThemeToggle } from "../ThemeToggle";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }) as unknown as typeof window.matchMedia;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ThemeToggle", () => {
  it("renders three theme options with Dark checked by default", async () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByRole("radio", { name: "Dark theme" })).toHaveAttribute("aria-checked", "true"));
    expect(screen.getByRole("radio", { name: "Light theme" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("radio", { name: "System theme" })).toHaveAttribute("aria-checked", "false");
  });

  it("clicking Light marks it checked and unchecks the others", async () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByRole("radio", { name: "Dark theme" })).toHaveAttribute("aria-checked", "true"));

    fireEvent.click(screen.getByRole("radio", { name: "Light theme" }));

    expect(screen.getByRole("radio", { name: "Light theme" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Dark theme" })).toHaveAttribute("aria-checked", "false");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("is a properly labeled radiogroup for accessibility", () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );
    expect(screen.getByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
  });
});
