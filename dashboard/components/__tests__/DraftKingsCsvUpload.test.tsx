import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DraftKingsCsvUpload } from "../DraftKingsCsvUpload";

const DATE = "2026-08-14";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

function csvFile(name = "DKSalaries.csv"): File {
  return new File(["Name,Salary\nAce,9000\n"], name, { type: "text/csv" });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DraftKingsCsvUpload", () => {
  it("rejects a non-.csv file client-side without calling the API", () => {
    render(<DraftKingsCsvUpload date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "salaries.png", { type: "image/png" })] } });
    expect(screen.getByText(/Only \.csv files are supported/i)).toBeInTheDocument();
  });

  it("uploads the file with the selected slate label and date", async () => {
    const impl = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => jsonResponse({ status: "ready", player_count: 171 }));
    vi.stubGlobal("fetch", impl);

    render(<DraftKingsCsvUpload date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile()] } });

    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => expect(impl).toHaveBeenCalled());
    const [url, init] = impl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/dfs-salaries/upload");
    const form = init.body as FormData;
    expect(form.get("date")).toBe(DATE);
    expect(form.get("slateLabel")).toBe("Main");
    expect((form.get("file") as File).name).toBe("DKSalaries.csv");

    expect(await screen.findByText(/Uploaded -- 171 players/)).toBeInTheDocument();
  });

  it("supports a custom slate label via 'Other'", async () => {
    const impl = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => jsonResponse({ status: "ready", player_count: 12 }));
    vi.stubGlobal("fetch", impl);

    render(<DraftKingsCsvUpload date={DATE} />);
    fireEvent.change(screen.getByLabelText(/Slate/i), { target: { value: "Other" } });
    fireEvent.change(screen.getByPlaceholderText("Slate name"), { target: { value: "Weekend Special" } });

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile()] } });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => expect(impl).toHaveBeenCalled());
    const form = (impl.mock.calls[0][1] as RequestInit).body as FormData;
    expect(form.get("slateLabel")).toBe("Weekend Special");
  });

  it("calls onUploaded and resets the form after a successful upload", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ status: "ready", player_count: 5 })));
    const onUploaded = vi.fn();

    render(<DraftKingsCsvUpload date={DATE} onUploaded={onUploaded} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile()] } });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => expect(onUploaded).toHaveBeenCalled());
  });

  it("shows the server's error reason on a failed upload", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ status: "error", reason: "DraftKings CSV does not look like a Classic MLB salary export." })));

    render(<DraftKingsCsvUpload date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile()] } });
    fireEvent.click(screen.getByText("Upload"));

    expect(await screen.findByText(/does not look like a Classic MLB salary export/)).toBeInTheDocument();
  });
});
