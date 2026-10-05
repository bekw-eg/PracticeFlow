import type { TeacherDocumentPreview } from "../../types/api";

export interface PreviewPage {
  number: number;
  section: number;
  element: HTMLElement;
  body: HTMLElement;
  annotations: HTMLElement;
}

function fragment(block: HTMLElement, range: Range): HTMLElement {
  const copy = block.cloneNode(false) as HTMLElement;
  copy.removeAttribute("id");
  copy.append(range.cloneContents());
  return copy;
}

function splitAt(block: HTMLElement, node: Node, offset: number): [HTMLElement, HTMLElement] {
  const before = document.createRange();
  before.selectNodeContents(block);
  before.setEnd(node, offset);
  const after = document.createRange();
  after.selectNodeContents(block);
  after.setStart(node, offset);
  const head = fragment(block, before);
  const tail = fragment(block, after);
  head.style.marginBottom = "0";
  tail.style.marginTop = "0";
  tail.style.textIndent = "0";
  tail.removeAttribute("data-page-break-before");
  return [head, tail];
}

function textBoundary(block: HTMLElement, offset: number): [Node, number] {
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (offset <= (node.textContent?.length ?? 0)) return [node, offset];
    offset -= node.textContent?.length ?? 0;
    node = walker.nextNode();
  }
  return [block, block.childNodes.length];
}

function fits(body: HTMLElement): boolean {
  const last = body.lastElementChild as HTMLElement | null;
  if (!last) return true;
  const bottom = last.getBoundingClientRect().bottom + (parseFloat(getComputedStyle(last).marginBottom) || 0);
  return bottom <= body.getBoundingClientRect().bottom + 1 && body.scrollHeight <= body.clientHeight + 1;
}

/** Split only at complete rows; paragraph/run attributes survive all copies. */
function splitTable(block: HTMLElement, body: HTMLElement): [HTMLElement, HTMLElement] | null {
  const rows = Array.from(block.querySelectorAll<HTMLTableRowElement>(":scope > tbody > tr"));
  if (rows.length < 2) return null;
  const safeCuts = Array.from({ length: rows.length - 1 }, (_, index) => index + 1).filter(cut =>
    rows.slice(0, cut).every((row, index) => Array.from(row.cells).every(cell => index + cell.rowSpan <= cut)));
  if (!safeCuts.length) return null;
  let low = 0;
  let high = safeCuts.length - 1;
  let best = 0;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const count = safeCuts[middle];
    const trial = block.cloneNode(true) as HTMLElement;
    Array.from(trial.querySelectorAll(":scope > tbody > tr")).slice(count).forEach((row) => row.remove());
    body.append(trial);
    const ok = fits(body);
    trial.remove();
    if (ok) { best = count; low = middle + 1; } else high = middle - 1;
  }
  // Keep the remaining rows at their normal size even if the first row is too tall.
  if (!best && !body.childElementCount) best = safeCuts[0];
  if (!best) return null;
  const head = block.cloneNode(true) as HTMLElement;
  const tail = block.cloneNode(true) as HTMLElement;
  Array.from(head.querySelectorAll(":scope > tbody > tr")).slice(best).forEach((row) => row.remove());
  Array.from(tail.querySelectorAll(":scope > tbody > tr")).slice(0, best).forEach((row) => row.remove());
  return [head, tail];
}

function splitParagraph(block: HTMLElement, body: HTMLElement): [HTMLElement, HTMLElement] | null {
  if (block.tagName !== "P") return null;
  const text = block.textContent ?? "";
  if (text.length < 2) return null;
  let low = 1;
  let high = text.length - 1;
  let best = 0;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const [head] = splitAt(block, ...textBoundary(block, middle));
    body.append(head);
    const ok = fits(body);
    head.remove();
    if (ok) { best = middle; low = middle + 1; } else high = middle - 1;
  }
  if (!best) return null;
  // Prefer a word boundary without dropping whitespace or parts of styled runs.
  const boundary = text.slice(0, best).search(/\s+\S*$/);
  if (boundary > best / 2) best = boundary + 1;
  return splitAt(block, ...textBoundary(block, best));
}

function splitExplicitBreaks(block: HTMLElement): Array<HTMLElement | null> {
  const marker = block.querySelector<HTMLElement>("[data-page-break]");
  if (!marker || block.tagName !== "P") return [block];
  const parent = marker.parentNode!;
  const offset = Array.from(parent.childNodes).indexOf(marker);
  const [head] = splitAt(block, parent, offset);
  const [, tail] = splitAt(block, parent, offset + 1);
  const hasContent = (node: HTMLElement) => !!node.textContent?.trim() || !!node.querySelector("br, [data-check-image]");
  return [
    ...(hasContent(head) ? [head] : []),
    null,
    ...(hasContent(tail) || tail.querySelector("[data-page-break]") ? splitExplicitBreaks(tail) : []),
  ];
}

/** Browser-measured pages; never infer a Word page number from a paragraph index. */
export async function paginateDocx(
  root: HTMLElement,
  preview: TeacherDocumentPreview,
  pageLabel: (number: number) => string,
  oversizedLabel: string,
  signal: AbortSignal,
): Promise<PreviewPage[]> {
  await document.fonts.ready;
  if (signal.aborted) return [];
  root.replaceChildren();
  const template = document.createElement("template");
  // This HTML comes only from the authenticated, escaping DOCX renderer.
  template.innerHTML = preview.html;
  await Promise.all(Array.from(template.content.querySelectorAll("img")).map(async (image) => {
    try { await image.decode(); } catch { /* browser will still render a safe placeholder */ }
  }));
  if (signal.aborted) return [];
  const sections = Array.from(template.content.children).filter((node) => node.tagName === "SECTION") as HTMLElement[];
  const pages: PreviewPage[] = [];
  for (const section of sections) {
    if (signal.aborted) return [];
    const number = (key: string, fallback: number, min: number, max: number) => {
      const value = Number(section.getAttribute(`data-${key}`) ?? fallback);
      return Number.isFinite(value) ? Math.max(min, Math.min(max, value)) : fallback;
    };
    const width = number("page-width", preview.page_width_mm, 100, 500);
    const height = number("page-height", preview.page_height_mm, 100, 500);
    const top = number("margin-top", preview.margin_top_mm, 0, height * 0.4);
    const bottom = number("margin-bottom", preview.margin_bottom_mm, 0, height * 0.4);
    const left = number("margin-left", preview.margin_left_mm, 0, width * 0.4);
    const right = number("margin-right", preview.margin_right_mm, 0, width * 0.4);
    const sectionIndex = number("section-index", 1, 1, 1000000);
    const createPage = () => {
      const element = document.createElement("article");
      element.className = "pf-docx-page";
      element.dataset.pageNumber = String(pages.length + 1);
      element.dataset.sectionIndex = String(sectionIndex);
      element.setAttribute("aria-label", pageLabel(pages.length + 1));
      Object.assign(element.style, {
        width: `${width}mm`, height: `${height}mm`,
        padding: `${top}mm ${right}mm ${bottom}mm ${left}mm`,
      });
      const body = document.createElement("section");
      body.className = "pf-docx-content";
      const annotations = document.createElement("div");
      annotations.className = "pf-docx-annotations";
      const footer = document.createElement("div");
      footer.className = "pf-docx-page-number";
      footer.textContent = pageLabel(pages.length + 1);
      element.append(body, annotations, footer);
      root.append(element);
      const page = { number: pages.length + 1, section: sectionIndex, element, body, annotations };
      pages.push(page);
      return page;
    };
    let page = createPage();
    const fitOversized = (block: HTMLElement) => {
      if (fits(page.body)) return;
      const style = getComputedStyle(block);
      const outerHeight = block.getBoundingClientRect().height
        + (parseFloat(style.marginTop) || 0) + (parseFloat(style.marginBottom) || 0);
      block.style.zoom = String(Math.min(1, (page.body.clientHeight - 2) / Math.max(1, outerHeight)));
      block.title = oversizedLabel;
    };
    const queue: Array<HTMLElement | null> = [];
    for (const block of Array.from(section.children) as HTMLElement[]) {
      queue.push(...splitExplicitBreaks(block));
    }
    for (let index = 0; index < queue.length; index++) {
      if (signal.aborted) return [];
      let block = queue[index];
      if (!block) { page = createPage(); continue; }
      if (block.dataset.pageBreakBefore === "true" && page.body.childElementCount) page = createPage();
      while (block) {
        if (signal.aborted) return [];
        page.body.append(block);
        if (fits(page.body)) break;
        block.remove();
        const split: [HTMLElement, HTMLElement] | null = splitTable(block, page.body) ?? splitParagraph(block, page.body);
        if (split) {
          page.body.append(split[0]);
          fitOversized(split[0]);
          block = split[1];
          page = createPage();
        } else if (page.body.childElementCount) {
          page = createPage();
        } else {
          // An indivisible object (for example a very tall table row) stays visible.
          page.body.append(block);
          fitOversized(block);
          break;
        }
        if (pages.length % 10 === 0) await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      }
      if (index % 40 === 0) await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    }
  }
  return pages;
}
