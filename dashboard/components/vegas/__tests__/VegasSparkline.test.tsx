import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VegasSparkline } from "../VegasSparkline";

describe("VegasSparkline", () => {
  it("renders a dashed flat line (no crash) when fewer than 2 points are given", () => {
    const { container } = render(<VegasSparkline points={[]} />);
    expect(container.querySelector("svg")).toBeTruthy();
    expect(container.querySelector("line")).toBeTruthy();
    expect(container.querySelector("path")).toBeFalsy();
  });

  it("renders a single-point series without crashing", () => {
    const { container } = render(<VegasSparkline points={[9.0]} />);
    expect(container.querySelector("svg")).toBeTruthy();
    expect(container.querySelector("line")).toBeTruthy();
  });

  it("renders a path for a real two-point series", () => {
    const { container } = render(<VegasSparkline points={[9.0, 9.7]} />);
    const path = container.querySelector("path");
    expect(path).toBeTruthy();
    expect(path?.getAttribute("d")).toMatch(/^M /);
  });

  it("never throws on NaN entries -- filters them out", () => {
    const { container } = render(<VegasSparkline points={[9.0, Number.NaN, 9.7]} />);
    expect(container.querySelector("path")).toBeTruthy();
  });
});
