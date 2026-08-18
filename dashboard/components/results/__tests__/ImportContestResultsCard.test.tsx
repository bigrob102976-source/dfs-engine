import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ImportContestResultsCard } from "../ImportContestResultsCard";

function makeFile(name = "contest.csv") {
  return new File(["Player,Roster Position\nJudge,OF"], name, { type: "text/csv" });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ImportContestResultsCard", () => {
  it("posts the file to /api/results/import-contest and shows a success summary", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ status: "ready", record_count: 150, matched_count: 145, match_rate: 0.9667, contest_name: "MLB $50K Main" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ImportContestResultsCard date="2026-08-17" slateId="dkcsv-main-2026-08-17" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeFile()] } });

    await waitFor(() => expect(screen.getByText(/Imported 150 rows for MLB \$50K Main/)).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/results/import-contest",
      expect.objectContaining({ method: "POST" }),
    );
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("date")).toBe("2026-08-17");
    expect(body.get("slateId")).toBe("dkcsv-main-2026-08-17");
  });

  it("shows the honest error reason when the import fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ json: () => Promise.resolve({ status: "error", reason: "No ownership snapshot found for this slate." }) }),
    );
    render(<ImportContestResultsCard date="2026-08-17" slateId={null} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeFile()] } });
    await waitFor(() => expect(screen.getByText("No ownership snapshot found for this slate.")).toBeInTheDocument());
  });
});
