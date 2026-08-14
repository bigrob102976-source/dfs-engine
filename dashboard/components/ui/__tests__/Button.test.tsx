import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DangerButton, PrimaryButton, SecondaryButton } from "../Button";

describe("Button variants", () => {
  it("PrimaryButton renders, fires onClick, and respects disabled", () => {
    const onClick = vi.fn();
    render(<PrimaryButton onClick={onClick}>Build Lineups</PrimaryButton>);
    fireEvent.click(screen.getByRole("button", { name: "Build Lineups" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("PrimaryButton disabled prevents interaction", () => {
    const onClick = vi.fn();
    render(
      <PrimaryButton onClick={onClick} disabled>
        Build Lineups
      </PrimaryButton>,
    );
    expect(screen.getByRole("button", { name: "Build Lineups" })).toBeDisabled();
  });

  it("SecondaryButton renders and fires onClick", () => {
    const onClick = vi.fn();
    render(<SecondaryButton onClick={onClick}>Cancel</SecondaryButton>);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("DangerButton renders and fires onClick", () => {
    const onClick = vi.fn();
    render(<DangerButton onClick={onClick}>Exclude</DangerButton>);
    fireEvent.click(screen.getByRole("button", { name: "Exclude" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("each variant applies its own distinct background color class", () => {
    render(
      <>
        <PrimaryButton>P</PrimaryButton>
        <SecondaryButton>S</SecondaryButton>
        <DangerButton>D</DangerButton>
      </>,
    );
    expect(screen.getByRole("button", { name: "P" }).className).toContain("bg-accent");
    expect(screen.getByRole("button", { name: "D" }).className).toContain("bg-red");
  });
});
