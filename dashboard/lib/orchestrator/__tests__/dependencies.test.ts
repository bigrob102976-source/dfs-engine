import { describe, expect, it } from "vitest";

import { resolveStepChain, STEP_ORDER } from "../dependencies";

describe("resolveStepChain", () => {
  it("a target with no dependencies resolves to just itself", () => {
    expect(resolveStepChain(["research"])).toEqual(["research"]);
  });

  it("pitchers pulls in research (its only dependency)", () => {
    expect(resolveStepChain(["pitchers"])).toEqual(["research", "pitchers"]);
  });

  it("batters pulls in research but NOT pitchers (siblings, not dependents)", () => {
    expect(resolveStepChain(["batters"])).toEqual(["research", "batters"]);
  });

  it("playerPool pulls in research, pitchers, batters, and dfsSalaries", () => {
    expect(resolveStepChain(["playerPool"])).toEqual(["research", "pitchers", "batters", "dfsSalaries", "playerPool"]);
  });

  it("ownership transitively pulls in the entire playerPool chain", () => {
    expect(resolveStepChain(["ownership"])).toEqual(["research", "pitchers", "batters", "dfsSalaries", "playerPool", "ownership"]);
  });

  it("optimizer pulls in absolutely everything", () => {
    expect(resolveStepChain(["optimizer"])).toEqual(STEP_ORDER);
  });

  it("multiple targets union their closures without duplicates, in pipeline order", () => {
    expect(resolveStepChain(["pitchers", "batters"])).toEqual(["research", "pitchers", "batters"]);
  });

  it("dfsSalaries alone does NOT pull in pitchers/batters (only depends on research)", () => {
    expect(resolveStepChain(["dfsSalaries"])).toEqual(["research", "dfsSalaries"]);
  });

  it("is idempotent for an already-complete target list", () => {
    expect(resolveStepChain(["research", "pitchers", "batters"])).toEqual(["research", "pitchers", "batters"]);
  });

  it("never duplicates a step that's both directly targeted and a dependency of another target", () => {
    const chain = resolveStepChain(["research", "playerPool"]);
    expect(chain.filter((s) => s === "research")).toHaveLength(1);
  });
});
