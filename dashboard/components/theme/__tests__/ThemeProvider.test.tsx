import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider, useTheme } from "../ThemeProvider";

const STORAGE_KEY = "bigmoney-theme";

function installMatchMedia(prefersLight: boolean) {
  const listeners: Array<(e: MediaQueryListEvent) => void> = [];
  const mql = {
    matches: prefersLight,
    media: "(prefers-color-scheme: light)",
    addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.push(cb),
    removeEventListener: vi.fn(),
  };
  window.matchMedia = vi.fn().mockReturnValue(mql) as unknown as typeof window.matchMedia;
  return {
    mql,
    // Real browsers update `matches` on the MediaQueryList itself before
    // firing the change event -- ThemeProvider re-queries matchMedia(...).matches
    // inside its handler rather than trusting the event payload, so the mock
    // must mutate the same object the mock's matchMedia() keeps returning.
    fireChange: (matches: boolean) => {
      mql.matches = matches;
      listeners.forEach((cb) => cb({ matches } as MediaQueryListEvent));
    },
  };
}

function Consumer() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button onClick={() => setTheme("light")}>Light</button>
      <button onClick={() => setTheme("dark")}>Dark</button>
      <button onClick={() => setTheme("system")}>System</button>
    </div>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ThemeProvider", () => {
  it("defaults to dark when nothing is stored (hard default, not OS-inferred)", async () => {
    installMatchMedia(true); // OS prefers light -- should NOT matter for the default
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("theme").textContent).toBe("dark"));
    expect(screen.getByTestId("resolved").textContent).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("switching to light updates resolvedTheme, the DOM attribute, and localStorage", async () => {
    installMatchMedia(false);
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("theme").textContent).toBe("dark"));

    act(() => screen.getByText("Light").click());

    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("light");
    await waitFor(() => expect(screen.getByTestId("resolved").textContent).toBe("light"));
  });

  it("switching to dark updates resolvedTheme, the DOM attribute, and localStorage", async () => {
    installMatchMedia(true);
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("theme").textContent).toBe("dark"));

    act(() => screen.getByText("Light").click());
    act(() => screen.getByText("Dark").click());

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    await waitFor(() => expect(screen.getByTestId("resolved").textContent).toBe("dark"));
  });

  it("system mode resolves from the OS preference (light)", async () => {
    installMatchMedia(true);
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("theme").textContent).toBe("dark"));

    act(() => screen.getByText("System").click());

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    await waitFor(() => expect(screen.getByTestId("resolved").textContent).toBe("light"));
  });

  it("system mode resolves from the OS preference (dark)", async () => {
    installMatchMedia(false);
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("theme").textContent).toBe("dark"));

    act(() => screen.getByText("System").click());

    expect(screen.getByTestId("resolved").textContent).toBe("dark");
  });

  it("system mode reacts live to an OS preference change", async () => {
    const { fireChange } = installMatchMedia(false);
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("theme").textContent).toBe("dark"));
    act(() => screen.getByText("System").click());
    expect(screen.getByTestId("resolved").textContent).toBe("dark");

    act(() => fireChange(true));
    expect(screen.getByTestId("resolved").textContent).toBe("light");
  });

  it("restores a previously persisted preference on mount", async () => {
    installMatchMedia(false);
    window.localStorage.setItem(STORAGE_KEY, "light");
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("theme").textContent).toBe("light"));
    await waitFor(() => expect(screen.getByTestId("resolved").textContent).toBe("light"));
  });

  it("useTheme throws when used outside a ThemeProvider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Consumer />)).toThrow(/useTheme must be used within a ThemeProvider/);
    spy.mockRestore();
  });
});
