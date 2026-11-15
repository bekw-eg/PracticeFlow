import { describe, expect, it } from "vitest";
import { layoutTabs, nextTabStop, parseTabStops, tabWidth } from "./tabStops";

describe("Word tab stops", () => {
  it("parses only whitelisted stops and sorts them", () => {
    expect(parseTabStops("164.84 right dot;10 left none;5 bar none;abc left none;20 center evil")).toEqual([
      { position: 10, alignment: "left", leader: "none" },
      { position: 20, alignment: "center", leader: "none" },
      { position: 164.84, alignment: "right", leader: "dot" },
    ]);
    expect(parseTabStops(undefined)).toEqual([]);
  });

  it("uses the next custom stop, then default stops beyond the last custom stop", () => {
    const stops = parseTabStops("10 left none;164.84 right dot");
    expect(nextTabStop(4, stops, 12.7)).toEqual(stops[0]);
    expect(nextTabStop(10, stops, 12.7)).toEqual(stops[1]);
    const fallback = nextTabStop(170, stops, 12.7);
    expect(fallback).toMatchObject({ alignment: "left", leader: "none" });
    expect(fallback.position).toBeCloseTo(177.8);
    expect(nextTabStop(0, [], Number.NaN).position).toBeCloseTo(12.7);
  });

  it("aligns the text after right and centre stops to the stop", () => {
    const right = { position: 164.84, alignment: "right" as const, leader: "dot" };
    // Table-of-contents line: title ends at 90 mm, page number is 4 mm wide.
    expect(tabWidth(90, right, 4, 170)).toBeCloseTo(70.84);
    expect(tabWidth(90, right, 4, 150)).toBeCloseTo(56);
    expect(tabWidth(90, { position: 100, alignment: "center", leader: "none" }, 10, 170)).toBeCloseTo(5);
    expect(tabWidth(120, right, 60, 170)).toBe(0);
    expect(tabWidth(3, { position: 10, alignment: "left", leader: "none" }, 99, 170)).toBeCloseTo(7);
  });

  it("keeps the CSS fallback width without a layout engine", () => {
    const paragraph = document.createElement("p");
    paragraph.innerHTML = 'A<span class="pf-tab">\t</span>5';
    document.body.append(paragraph);
    layoutTabs(paragraph);
    expect(paragraph.querySelector<HTMLElement>(".pf-tab")!.style.width).toBe("");
    paragraph.remove();
  });
});
