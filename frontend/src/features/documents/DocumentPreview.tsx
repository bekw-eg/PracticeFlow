import { useLayoutEffect, useRef, useState } from "react";
import type { DocumentModel, Section } from "../../types/document";
import { A4Page } from "./A4Page";
import { BlockView } from "./BlockView";
import { useTranslation } from "react-i18next";

const PAGE_GAP_PX = 24;

function pagePosition(index: number, pageWidthMm: number) {
  return index === 0 ? "0" : `calc(${index * pageWidthMm}mm + ${index * PAGE_GAP_PX}px)`;
}

/**
 * Browser pagination for the A4 preview. The content is a single CSS
 * multi-column flow whose columns are exactly the printable area of one A4
 * page. Browser line layout therefore decides where a paragraph wraps and
 * where a long paragraph continues on the next page; we never split runs,
 * words, or inline nodes into independent layout blocks.
 */
export function DocumentPreview({ document, numbering }: { document: DocumentModel; numbering: Record<string, string> }) {
  const { t } = useTranslation("editor");
  const flowRef = useRef<HTMLDivElement>(null);
  const [pageCount, setPageCount] = useState(1);
  const { margins } = document.meta;
  const isLandscape = document.meta.orientation === "landscape";
  const pageWidthMm = isLandscape ? 297 : 210;
  const pageHeightMm = isLandscape ? 210 : 297;
  const contentWidthMm = pageWidthMm - margins.left_mm - margins.right_mm;
  const contentHeightMm = pageHeightMm - margins.top_mm - margins.bottom_mm;

  useLayoutEffect(() => {
    const flow = flowRef.current;
    if (!flow) return;

    const measurePages = () => {
      const pageWidthPx = flow.getBoundingClientRect().width;
      const pageStepPx = pageWidthPx + PAGE_GAP_PX;
      const needed = pageWidthPx > 0 ? Math.max(1, Math.ceil((flow.scrollWidth + PAGE_GAP_PX) / pageStepPx)) : 1;
      setPageCount((current) => (current === needed ? current : needed));
    };

    measurePages();
    const frame = requestAnimationFrame(measurePages);
    const observer = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(measurePages);
    observer?.observe(flow);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, [contentHeightMm, contentWidthMm, document, pageWidthMm]);

  const previewWidth = `calc(${pageCount * pageWidthMm}mm + ${Math.max(0, pageCount - 1) * PAGE_GAP_PX}px)`;

  return (
    <div role="region" className="overflow-x-auto pb-6" aria-label={t("documentPreview")}>
      <div className="relative" style={{ width: previewWidth, minHeight: `${pageHeightMm}mm` }}>
        {Array.from({ length: pageCount }, (_, pageIndex) => (
          <A4Page
            key={pageIndex}
            marginTopMm={margins.top_mm}
            marginBottomMm={margins.bottom_mm}
            marginLeftMm={margins.left_mm}
            marginRightMm={margins.right_mm}
            orientation={document.meta.orientation}
            className="absolute top-0 !m-0"
            style={{ left: pagePosition(pageIndex, pageWidthMm), height: `${pageHeightMm}mm`, minHeight: `${pageHeightMm}mm` }}
          >
            <span aria-hidden="true" />
          </A4Page>
        ))}

        <div
          ref={flowRef}
          className="relative z-10"
          style={{
            boxSizing: "border-box",
            width: `${pageWidthMm}mm`,
            height: `${pageHeightMm}mm`,
            paddingTop: `${margins.top_mm}mm`,
            paddingBottom: `${margins.bottom_mm}mm`,
            paddingLeft: `${margins.left_mm}mm`,
            paddingRight: `${margins.right_mm}mm`,
            columnWidth: `${contentWidthMm}mm`,
            columnGap: `calc(${margins.left_mm + margins.right_mm}mm + ${PAGE_GAP_PX}px)`,
            columnFill: "auto",
            overflow: "visible",
          }}
        >
          {document.title_page && (
            <section
              aria-label={t("coverPage")}
              style={{ minHeight: `${contentHeightMm}mm`, display: "flex", flexDirection: "column", justifyContent: "center", breakAfter: "column" }}
            >
              {document.title_page.blocks.map((block) => (
                <BlockView key={block.id} block={block} meta={document.meta} />
              ))}
            </section>
          )}

          {document.sections.map((section, sectionIndex) => (
            <PreviewSection
              key={section.id}
              section={section}
              sectionIndex={sectionIndex}
              meta={document.meta}
              numbering={numbering}
            />
          ))}
        </div>

        {Array.from({ length: pageCount }, (_, pageIndex) => (
          <div
            key={pageIndex}
            aria-hidden="true"
            className="pointer-events-none absolute bottom-[8mm] z-20 text-center text-xs text-[var(--color-muted)]"
            style={{ left: pagePosition(pageIndex, pageWidthMm), width: `${pageWidthMm}mm` }}
          >
            — {pageIndex + 1} —
          </div>
        ))}
      </div>
    </div>
  );
}

function PreviewSection({
  section,
  sectionIndex,
  meta,
  numbering,
}: {
  section: Section;
  sectionIndex: number;
  meta: DocumentModel["meta"];
  numbering: Record<string, string>;
}) {
  const { t } = useTranslation("editor");
  return (
    <section style={sectionIndex > 0 && section.page_break_before ? { breakBefore: "column" } : undefined}>
      <h2 className="mb-3" style={{ fontFamily: meta.default_font, fontWeight: 700, fontSize: "16pt" }}>
        {numbering[section.id] && <span className="mr-2 text-[var(--color-muted)]">{numbering[section.id]}</span>}
        {section.title}
      </h2>
      {section.blocks.map((block) =>
        block.type === "pageBreak" ? (
          <div key={block.id} role="separator" aria-label={t("pageBreak")} style={{ breakBefore: "column" }} />
        ) : (
          <BlockView key={block.id} block={block} meta={meta} numberPrefix={numbering[block.id]} />
        )
      )}
    </section>
  );
}
