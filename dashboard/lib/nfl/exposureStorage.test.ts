import { beforeEach, describe, expect, it } from "vitest";

import { loadExposureState, saveExposureState } from "./exposureStorage";

describe("exposureStorage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns empty state when nothing saved yet", () => {
    expect(loadExposureState(151307)).toEqual({ maxExposure: {}, minExposure: {} });
  });

  it("round-trips real DraftKings player identity fractions", () => {
    saveExposureState(151307, { maxExposure: { "1214154": 0.25 }, minExposure: { "877745": 0.5 } });
    expect(loadExposureState(151307)).toEqual({ maxExposure: { "1214154": 0.25 }, minExposure: { "877745": 0.5 } });
  });

  it("keeps state scoped per DraftGroup -- a slate switch never leaks exposure overrides", () => {
    saveExposureState(151307, { maxExposure: { "1214154": 0.25 }, minExposure: {} });
    expect(loadExposureState(999999)).toEqual({ maxExposure: {}, minExposure: {} });
  });
});
