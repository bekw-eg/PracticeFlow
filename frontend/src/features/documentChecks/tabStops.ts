/**
 * Word-like tab layout for the DOCX preview.
 *
 * The backend marks each Word tab as an empty `.pf-tab` span and serializes the
 * paragraph's tab stops (positions in mm from the text margin). Text widths are
 * only known in the browser, so the paginator sizes every tab after the block
 * is placed on a page: left stops move the following text to the stop, right
 * and decimal stops end the following text at the stop (table-of-contents page
 * numbers), centre stops centre it.
 */
export type TabAlignment = "left" | "right" | "center" | "decimal";

export interface TabStop {
  position: number;
  alignment: TabAlignment;
  leader: string;
}

export const DEFAULT_TAB_STOP_MM = 12.7;
const ALIGNMENTS = new Set<string>(["left", "right", "center", "decimal"]);
const LEADERS = new Set<string>(["none", "dot", "hyphen", "underscore", "heavy", "middleDot"]);
const EPSILON_MM = 0.05;

export function parseTabStops(value: string | null | undefined): TabStop[] {
  if (!value) return [];
  return value.split(";").flatMap((item) => {
    const [rawPosition, alignment, leader] = item.trim().split(/\s+/);
    const position = Number(rawPosition);
    if (!Number.isFinite(position) || position < 0 || position > 600 || !ALIGNMENTS.has(alignment)) return [];
    return [{ position, alignment: alignment as TabAlignment, leader: LEADERS.has(leader) ? leader : "none" }];
  }).sort((first, second) => first.position - second.position);
}

/** Word ignores default stops left of a custom stop, so the first custom stop to the right wins. */
export function nextTabStop(x: number, stops: TabStop[], defaultTab: number): TabStop {
  const custom = stops.find((stop) => stop.position > x + EPSILON_MM);
  if (custom) return custom;
  const step = Number.isFinite(defaultTab) && defaultTab >= 1 ? defaultTab : DEFAULT_TAB_STOP_MM;
  return { position: (Math.floor((x + EPSILON_MM) / step) + 1) * step, alignment: "left", leader: "none" };
}

/** Width (mm) of a tab starting at `x` whose following text segment is `following` mm wide. */
export function tabWidth(x: number, stop: TabStop, following: number, lineEnd: number): number {
  const position = Math.min(stop.position, lineEnd);
  const shift = stop.alignment === "left" ? 0 : stop.alignment === "center" ? following / 2 : following;
  return Math.max(0, position - shift - x);
}

function layoutParagraph(paragraph: HTMLElement, tabs: HTMLElement[]): void {
  const probe = document.createElement("span");
  probe.style.cssText = "position:absolute;display:block;width:100mm;height:0;visibility:hidden";
  paragraph.append(probe);
  const pixelsPerMm = probe.getBoundingClientRect().width / 100;
  probe.remove();
  if (!(pixelsPerMm > 0)) return; // No layout engine (for example jsdom): keep the CSS fallback width.

  // Tab positions are measured from the text margin of the containing block, not the indent.
  const margin = document.createElement("div");
  margin.style.cssText = "display:block;height:0;margin:0;padding:0;border:0";
  paragraph.before(margin);
  const origin = margin.getBoundingClientRect().left;
  margin.remove();
  const lineEnd = (paragraph.getBoundingClientRect().right - origin) / pixelsPerMm;
  const stops = parseTabStops(paragraph.dataset.tabStops);
  const defaultTab = Number(paragraph.closest<HTMLElement>("[data-default-tab]")?.dataset.defaultTab);

  for (const tab of tabs) tab.style.width = "0mm";
  tabs.forEach((tab, index) => {
    const x = (tab.getBoundingClientRect().left - origin) / pixelsPerMm;
    const absolute = tab.dataset.ptab;
    const stop: TabStop = absolute && ALIGNMENTS.has(absolute)
      ? {
        position: absolute === "right" ? lineEnd : absolute === "center" ? lineEnd / 2 : 0,
        alignment: absolute as TabAlignment,
        leader: tab.dataset.ptabLeader ?? "none",
      }
      : nextTabStop(x, stops, defaultTab);
    let following = 0;
    if (stop.alignment !== "left") {
      const range = document.createRange();
      range.setStartAfter(tab);
      const next = tabs[index + 1];
      if (next) range.setEndBefore(next);
      else range.setEnd(paragraph, paragraph.childNodes.length);
      following = range.getBoundingClientRect().width / pixelsPerMm;
    }
    tab.style.width = `${tabWidth(x, stop, following, lineEnd).toFixed(2)}mm`;
    if (LEADERS.has(stop.leader) && stop.leader !== "none") tab.dataset.leader = stop.leader;
    else delete tab.dataset.leader;
  });
}

/** Size every Word tab inside a block that is attached to a laid-out page. */
export function layoutTabs(block: HTMLElement): void {
  const tabs = Array.from(block.querySelectorAll<HTMLElement>(".pf-tab"));
  if (!tabs.length) return;
  const byParagraph = new Map<HTMLElement, HTMLElement[]>();
  for (const tab of tabs) {
    const paragraph = tab.closest<HTMLElement>("p") ?? block;
    byParagraph.set(paragraph, [...(byParagraph.get(paragraph) ?? []), tab]);
  }
  for (const [paragraph, paragraphTabs] of byParagraph) layoutParagraph(paragraph, paragraphTabs);
}
