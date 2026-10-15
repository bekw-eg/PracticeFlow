import type { DocumentPageLayout } from "../../types/api";
import type { PreviewPage } from "./paginateDocx";

/** Retain every occurrence: one paragraph/run can continue on several pages. */
export function collectPageLayout(pages: PreviewPage[]): DocumentPageLayout[] {
  return pages.map(page => {
    const paragraphs: Record<string, number[]> = {};
    for (const paragraph of page.body.querySelectorAll<HTMLElement>("[data-paragraph-index]")) {
      const index = paragraph.dataset.paragraphIndex!;
      const runs = Array.from(paragraph.querySelectorAll<HTMLElement>("[data-run-index]"))
        .filter(run => Array.from(run.querySelectorAll<HTMLElement>(
          '[data-check-text]:not([data-check-excluded="true"]), [data-check-image]:not([data-check-excluded="true"])',
        )).some(node => node.hasAttribute("data-check-image") || node.textContent?.trim()))
        .map(run => Number(run.dataset.runIndex));
      paragraphs[index] = [...new Set([...(paragraphs[index] ?? []), ...runs])].sort((a, b) => a - b);
    }
    return { number: page.number, section_index: page.section, paragraphs };
  });
}
