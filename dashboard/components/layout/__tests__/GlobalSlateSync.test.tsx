import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockReplace = vi.fn();
let mockPathname = "/dashboard/pitchers";
let mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  usePathname: () => mockPathname,
  useSearchParams: () => mockSearchParams,
}));

import { readStoredSlateId, writeStoredSlateId } from "@/lib/globalSlateStorage";

import { GlobalSlateSync } from "../GlobalSlateSync";

beforeEach(() => {
  window.localStorage.clear();
  mockReplace.mockClear();
  mockPathname = "/dashboard/pitchers";
  mockSearchParams = new URLSearchParams();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GlobalSlateSync", () => {
  it("does nothing when the URL already has ?slate= and nothing is stored", async () => {
    mockSearchParams = new URLSearchParams("slate=turbo");
    render(<GlobalSlateSync />);
    await waitFor(() => expect(readStoredSlateId()).toBe("turbo"));
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("restores the last stored slate when the URL has no ?slate= at all", async () => {
    writeStoredSlateId("dkunofficial-152547");
    mockSearchParams = new URLSearchParams();
    render(<GlobalSlateSync />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard/pitchers?slate=dkunofficial-152547"));
  });

  it("preserves other existing query params while restoring the stored slate", async () => {
    writeStoredSlateId("main");
    mockSearchParams = new URLSearchParams("player=123");
    render(<GlobalSlateSync />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard/pitchers?player=123&slate=main"));
  });

  it("never restores when nothing has been explicitly stored", async () => {
    mockSearchParams = new URLSearchParams();
    render(<GlobalSlateSync />);
    await waitFor(() => expect(readStoredSlateId()).toBeNull());
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("never overwrites an explicit ?slate= already present in the URL -- URL always wins", async () => {
    writeStoredSlateId("stale-slate");
    mockSearchParams = new URLSearchParams("slate=fresh-slate");
    render(<GlobalSlateSync />);
    await waitFor(() => expect(readStoredSlateId()).toBe("fresh-slate"));
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
