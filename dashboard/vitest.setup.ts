import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Explicit cleanup registration: @testing-library/react's auto-cleanup
// relies on a global `afterEach` being present, which only happens with
// `test.globals: true`. This project imports test functions explicitly
// instead, so cleanup must be wired up here or DOM trees leak between
// tests within the same file (causing "multiple elements found" errors).
afterEach(() => {
  cleanup();
});
