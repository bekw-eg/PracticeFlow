import { expect, it } from "vitest";
import { collectPageLayout } from "./pageLayout";
import type { PreviewPage } from "./paginateDocx";

it("keeps shared source locations and ignores cover text and empty split run fragments", () => {
  const pages = [
    '<p data-paragraph-index="1"><span data-run-index="1"><span data-check-text data-check-excluded="true">Cover</span></span></p>',
    '<p data-paragraph-index="2"><span data-run-index="1"><span data-check-text>First</span></span><span data-run-index="2"></span></p>',
    '<table><tbody><tr><td><p data-paragraph-index="2"><span data-run-index="1"><span data-check-text>Rest</span></span><span data-run-index="2"><span data-check-text>End</span></span></p></td></tr></tbody></table>',
  ].map((html, index): PreviewPage => {
    const body = document.createElement("section");
    body.innerHTML = html;
    return { number: index + 1, section: 1, body, element: document.createElement("article"), annotations: document.createElement("div") };
  });
  expect(collectPageLayout(pages)).toEqual([
    { number: 1, section_index: 1, paragraphs: { "1": [] } },
    { number: 2, section_index: 1, paragraphs: { "2": [1] } },
    { number: 3, section_index: 1, paragraphs: { "2": [1, 2] } },
  ]);
});
