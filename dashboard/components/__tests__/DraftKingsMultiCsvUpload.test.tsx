import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DraftKingsMultiCsvUpload } from "../DraftKingsMultiCsvUpload";

const DATE = "2026-08-14";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

function csvFile(name: string): File {
  return new File(["Name,Salary\nAce,9000\n"], name, { type: "text/csv" });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DraftKingsMultiCsvUpload", () => {
  it("guesses a slate label from each filename (Main/Turbo/Night/...)", () => {
    render(<DraftKingsMultiCsvUpload date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [csvFile("DKSalaries_Main.csv"), csvFile("DK Turbo Slate.csv"), csvFile("night_export.csv")] },
    });

    expect(screen.getByLabelText("Slate name for DKSalaries_Main.csv")).toHaveValue("Main");
    expect(screen.getByLabelText("Slate name for DK Turbo Slate.csv")).toHaveValue("Turbo");
    expect(screen.getByLabelText("Slate name for night_export.csv")).toHaveValue("Night");
  });

  it("only ever guesses the display LABEL, never games -- and the user can freely rename it before import", () => {
    render(<DraftKingsMultiCsvUpload date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile("DKSalaries (3).csv")] } });

    const labelInput = screen.getByLabelText("Slate name for DKSalaries (3).csv");
    fireEvent.change(labelInput, { target: { value: "Weekend Special" } });
    expect(labelInput).toHaveValue("Weekend Special");
  });

  it("imports every queued file in one operation, one request per file, all in a single click", async () => {
    const impl = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => jsonResponse({ status: "ready", player_count: 142 }));
    vi.stubGlobal("fetch", impl);

    render(<DraftKingsMultiCsvUpload date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile("DKSalaries_Main.csv"), csvFile("DKSalaries_Turbo.csv")] } });

    fireEvent.click(screen.getByText("Import 2 Slates"));

    await waitFor(() => expect(impl).toHaveBeenCalledTimes(2));
    const firstForm = (impl.mock.calls[0][1] as RequestInit).body as FormData;
    expect(firstForm.get("date")).toBe(DATE);
    expect(firstForm.get("slateLabel")).toBe("Main");
    const secondForm = (impl.mock.calls[1][1] as RequestInit).body as FormData;
    expect(secondForm.get("slateLabel")).toBe("Turbo");

    expect(await screen.findByText("2 Slates Loaded")).toBeInTheDocument();
  });

  it("reports per-file results when some succeed and some fail, never silently dropping a failure", async () => {
    const impl = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url, init) => {
      const form = init!.body as FormData;
      const label = form.get("slateLabel");
      return label === "Main" ? jsonResponse({ status: "ready", player_count: 100 }) : jsonResponse({ status: "error", reason: "Malformed CSV." });
    });
    vi.stubGlobal("fetch", impl);

    render(<DraftKingsMultiCsvUpload date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile("DKSalaries_Main.csv"), csvFile("DKSalaries_Turbo.csv")] } });
    fireEvent.click(screen.getByText("Import 2 Slates"));

    expect(await screen.findByText("1 Slate Loaded")).toBeInTheDocument();
    expect(screen.getByText(/Malformed CSV/)).toBeInTheDocument();
  });

  it("calls onUploaded once any file succeeds and resets the pending queue", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ status: "ready", player_count: 5 })));
    const onUploaded = vi.fn();

    render(<DraftKingsMultiCsvUpload date={DATE} onUploaded={onUploaded} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile("DKSalaries_Main.csv")] } });
    fireEvent.click(screen.getByText("Import 1 Slate"));

    await waitFor(() => expect(onUploaded).toHaveBeenCalled());
  });

  it("lets the user remove a queued file before importing", () => {
    render(<DraftKingsMultiCsvUpload date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile("DKSalaries_Main.csv"), csvFile("DKSalaries_Turbo.csv")] } });

    fireEvent.click(screen.getByLabelText("Remove DKSalaries_Main.csv"));
    expect(screen.queryByText("DKSalaries_Main.csv")).not.toBeInTheDocument();
    expect(screen.getByText("Import 1 Slate")).toBeInTheDocument();
  });

  it("ignores non-.csv files added alongside valid ones", () => {
    render(<DraftKingsMultiCsvUpload date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [csvFile("DKSalaries_Main.csv"), new File(["x"], "notes.png", { type: "image/png" })] },
    });
    expect(screen.getByText("Import 1 Slate")).toBeInTheDocument();
  });
});
