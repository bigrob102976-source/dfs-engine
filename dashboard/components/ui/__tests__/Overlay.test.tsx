import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Drawer } from "../Drawer";
import { Modal } from "../Modal";
import { Tooltip } from "../Tooltip";

describe("Modal", () => {
  it("renders its children in a labeled dialog", () => {
    render(
      <Modal onClose={vi.fn()} ariaLabel="Player detail">
        <div>modal content</div>
      </Modal>,
    );
    expect(screen.getByRole("dialog", { name: "Player detail" })).toBeInTheDocument();
    expect(screen.getByText("modal content")).toBeInTheDocument();
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose} ariaLabel="Player detail">
        <div>modal content</div>
      </Modal>,
    );
    fireEvent.click(screen.getByRole("dialog").parentElement!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not call onClose when clicking inside the dialog content", () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose} ariaLabel="Player detail">
        <div>modal content</div>
      </Modal>,
    );
    fireEvent.click(screen.getByText("modal content"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose} ariaLabel="Player detail">
        <div>modal content</div>
      </Modal>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("Drawer", () => {
  it("renders its children in a labeled dialog anchored to the side", () => {
    render(
      <Drawer onClose={vi.fn()} ariaLabel="Kyle Schwarber player detail">
        <div>drawer content</div>
      </Drawer>,
    );
    expect(screen.getByRole("dialog", { name: "Kyle Schwarber player detail" })).toBeInTheDocument();
    expect(screen.getByText("drawer content")).toBeInTheDocument();
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    render(
      <Drawer onClose={onClose} ariaLabel="detail">
        <div>drawer content</div>
      </Drawer>,
    );
    fireEvent.click(screen.getByRole("dialog").parentElement!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    render(
      <Drawer onClose={onClose} ariaLabel="detail">
        <div>drawer content</div>
      </Drawer>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("Tooltip", () => {
  it("renders the trigger and a hidden-until-hover label", () => {
    render(
      <Tooltip label="Adjusted vs. baseline">
        <button>Δ</button>
      </Tooltip>,
    );
    expect(screen.getByRole("button", { name: "Δ" })).toBeInTheDocument();
    expect(screen.getByRole("tooltip")).toHaveTextContent("Adjusted vs. baseline");
  });
});
