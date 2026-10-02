import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { DocumentCheckFinding, ParagraphType, TeacherDocumentPreview } from "../../types/api";
import { paginateDocx, type PreviewPage } from "./paginateDocx";

export interface FindingPosition {
  pages: number[];
  excerpt: string;
}

type Props = {
  preview: TeacherDocumentPreview;
  findings: DocumentCheckFinding[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onPositions: (positions: Record<string, FindingPosition>) => void;
  excludeFirstPage: boolean;
  paragraphTypes?: Record<number, ParagraphType>;
  selectedParagraphIndex?: number;
  paragraphSelectionEnabled?: boolean;
  onParagraphSelect?: (paragraph: { index: number; text: string }) => void;
};

const rank = { INFO: 1, WARNING: 2, ERROR: 3 };
const positiveIndex = (value: unknown) => {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
};

export function PaginatedDocument({ preview, findings, selectedId, onSelect, onPositions, excludeFirstPage,
  paragraphTypes, selectedParagraphIndex, paragraphSelectionEnabled, onParagraphSelect }: Props) {
  const { t } = useTranslation("documentChecks");
  const root = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<PreviewPage[]>([]);
  const [building, setBuilding] = useState(true);
  const [failed, setFailed] = useState(false);
  const targets = useRef(new Map<string, HTMLElement[]>());

  useEffect(() => {
    const controller = new AbortController();
    if (!root.current) return;
    setBuilding(true);
    setFailed(false);
    setPages([]);
    void paginateDocx(root.current, preview, (number) => t("previewPage", { number }), t("oversizedBlock"), controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) { setPages(result); setBuilding(false); }
      }).catch(() => {
        if (!controller.signal.aborted) { setFailed(true); setBuilding(false); }
      });
    return () => controller.abort();
  }, [preview, t]);

  useEffect(() => {
    if (building) return;
    for (const image of Array.from(root.current?.querySelectorAll<HTMLImageElement>("img[data-preview-label]") ?? [])) {
      const key = image.dataset.previewLabel;
      image.alt = key === "imageUnavailable" ? t("imageUnavailable", { defaultValue: "Image unavailable" }) : t("embeddedImage", { defaultValue: "Embedded image" });
    }
    const positions: Record<string, FindingPosition> = {};
    const targetMap = new Map<string, HTMLElement[]>();
    const groups = new Map<HTMLElement, { page: PreviewPage; items: DocumentCheckFinding[]; side?: string }>();
    const paragraphs = new Map<number, Array<{ node: HTMLElement; page: PreviewPage }>>();
    const checkedText = (node: HTMLElement) => Array.from(node.querySelectorAll<HTMLElement>('[data-check-text]:not([data-check-excluded="true"])'))
      .filter((text) => text.textContent?.trim());
    const hasCheckedContent = (node: HTMLElement) => checkedText(node).length > 0
      || !!node.querySelector('[data-check-image]:not([data-check-excluded="true"])');
    for (const page of pages) {
      page.annotations.replaceChildren();
      if (excludeFirstPage && !hasCheckedContent(page.body) && page.body.querySelector('[data-check-excluded="true"]')) {
        const label = document.createElement("div");
        label.className = "pf-docx-excluded-label";
        label.textContent = t("titlePageExcluded");
        page.annotations.append(label);
      }
      page.body.querySelectorAll<HTMLElement>("[data-paragraph-index]").forEach((node) => {
        const key = Number(node.dataset.paragraphIndex);
        paragraphs.set(key, [...(paragraphs.get(key) ?? []), { node, page }]);
      });
      page.body.querySelectorAll<HTMLElement>(".pf-docx-error-location").forEach((node) => {
        node.classList.remove("pf-docx-error-location");
        delete node.dataset.severity;
        delete node.dataset.findingIds;
        node.removeAttribute("title");
        node.removeAttribute("aria-label");
      });
    }
    for (const finding of findings) {
      const paragraph = positiveIndex(finding.location.paragraph_index);
      const run = positiveIndex(finding.location.run_index);
      const section = positiveIndex(finding.location.section_index);
      const located: Array<{ node: HTMLElement; page: PreviewPage; side?: string }> = [];
      // Unknown locations never fall back to page one.
      if ((!finding.location.part || finding.location.part === "word/document.xml") && paragraph) {
        for (const item of paragraphs.get(paragraph) ?? []) {
          if (run) {
            item.node.querySelectorAll<HTMLElement>(`[data-run-index="${run}"]`).forEach((node) => {
              const matches = excludeFirstPage ? checkedText(node) : [node];
              for (const match of matches) if (match.textContent?.trim()) located.push({ node: match, page: item.page });
            });
          } else if (!excludeFirstPage || checkedText(item.node).length) {
            if (excludeFirstPage && item.node.querySelector('[data-check-excluded="true"]')) {
              for (const node of checkedText(item.node)) located.push({ node, page: item.page });
            } else located.push(item);
          }
        }
      } else if (section && (!finding.location.part || finding.location.part === "word/document.xml")) {
        const side = /^margin_(top|right|bottom|left)$/.exec(finding.property_name)?.[1];
        for (const page of pages.filter((page) => page.section === section)) {
          if (excludeFirstPage && !hasCheckedContent(page.body)) continue;
          const region = document.createElement("div");
          region.className = `pf-docx-page-issue ${side ? `pf-docx-margin-${side}` : "pf-docx-format-issue"}`;
          if (side) region.style.setProperty("--margin-size", getComputedStyle(page.element).getPropertyValue(`padding-${side}`));
          page.annotations.append(region);
          located.push({ node: region, page, side });
        }
      }
      positions[finding.id] = {
        pages: [...new Set(located.map((item) => item.page.number))],
        excerpt: paragraph ? (located.map((item) => item.node.textContent ?? "").join(" ").replace(/\s+/g, " ").trim().slice(0, 140)) : "",
      };
      targetMap.set(finding.id, located.map((item) => item.node));
      for (const item of located) {
        const group = groups.get(item.node) ?? { page: item.page, items: [], side: item.side };
        group.items.push(finding);
        groups.set(item.node, group);
      }
    }
    const removers: Array<() => void> = [];
    const markerRows = new Map<PreviewPage, Map<number, { nodes: HTMLElement[]; items: DocumentCheckFinding[] }>>();
    const connect = (element: HTMLElement, items: DocumentCheckFinding[]) => {
      let next = 0;
      const title = items.map((finding) => `№${finding.sequence} · ${t(`findingCodes.${finding.code}` as never, { defaultValue: finding.code })}`).join("\n");
      element.title = title;
      element.setAttribute("aria-label", title);
      element.dataset.findingIds = items.map((item) => item.id).join(" ");
      const click = (event: MouseEvent) => { event.stopPropagation(); onSelect(items[next % items.length].id); next++; };
      element.addEventListener("click", click);
      removers.push(() => element.removeEventListener("click", click));
    };
    for (const [node, group] of groups) {
      const severity = group.items.reduce((value, finding) => rank[finding.severity] > rank[value] ? finding.severity : value, "INFO" as DocumentCheckFinding["severity"]);
      node.classList.add("pf-docx-error-location");
      node.dataset.severity = severity;
      connect(node, group.items);
      const page = group.page;
      if (node.classList.contains("pf-docx-page-issue")) {
        const marker = document.createElement("button");
        marker.type = "button";
        marker.className = "pf-docx-margin-label";
        marker.textContent = `№${group.items[0].sequence} · ${t(`findingProperties.${group.items[0].property_name}` as never, { defaultValue: t("pageSettingsIssue") })}`;
        node.append(marker);
        continue;
      }
      const row = Math.round((node.getBoundingClientRect().top - page.element.getBoundingClientRect().top) / 22) * 22;
      const rows = markerRows.get(page) ?? new Map();
      const entry: { nodes: HTMLElement[]; items: DocumentCheckFinding[] } = rows.get(row) ?? { nodes: [], items: [] };
      entry.nodes.push(node);
      for (const item of group.items) if (!entry.items.some((existing) => existing.id === item.id)) entry.items.push(item);
      rows.set(row, entry);
      markerRows.set(page, rows);
    }
    for (const [page, rows] of markerRows) for (const [row, entry] of rows) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "pf-docx-error-badge";
      button.style.top = `${Math.max(2, Math.min(page.element.clientHeight - 28, row))}px`;
      button.textContent = `! ${entry.items[0].sequence}${entry.items.length > 1 ? ` +${entry.items.length - 1}` : ""}`;
      connect(button, entry.items);
      page.annotations.append(button);
    }
    targets.current = targetMap;
    onPositions(positions);
    return () => removers.forEach((remove) => remove());
  }, [pages, findings, building, onPositions, onSelect, excludeFirstPage, t]);

  useEffect(() => {
    if (building) return;
    root.current?.querySelectorAll(".pf-docx-selected").forEach((node) => node.classList.remove("pf-docx-selected"));
    const matches = selectedId ? targets.current.get(selectedId) ?? [] : [];
    for (const node of matches) node.classList.add("pf-docx-selected");
    matches[0]?.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
  }, [selectedId, pages, findings, building, excludeFirstPage]);

  useEffect(() => {
    if (building || !root.current) return;
    const container = root.current;
    const nodes = Array.from(container.querySelectorAll<HTMLElement>("[data-paragraph-index]"));
    const findingLabels = new Map(findings.map(finding => [finding.id,
      `№${finding.sequence} · ${t(`findingCodes.${finding.code}` as never, { defaultValue: finding.code })}`]));
    for (const node of nodes) {
      const index = Number(node.dataset.paragraphIndex);
      const kind = paragraphTypes?.[index];
      node.classList.toggle("pf-docx-paragraph-selected", !!paragraphSelectionEnabled && index === selectedParagraphIndex);
      node.classList.toggle("pf-docx-paragraph-selectable", !!paragraphSelectionEnabled);
      if (kind) node.dataset.paragraphType = kind;
      if (paragraphSelectionEnabled) {
        node.tabIndex = 0;
        node.setAttribute("role", "button");
        const label = `${t("findingParagraph", { number: index })}: ${kind ? t(`paragraphTypes.${kind}`) : t("paragraphType")}`;
        node.setAttribute("aria-label", label);
        node.title = label;
      } else {
        node.removeAttribute("tabindex");
        node.removeAttribute("role");
        const label = (node.dataset.findingIds?.split(" ") ?? []).map(id => findingLabels.get(id)).filter(Boolean).join("\n");
        if (label) { node.title = label; node.setAttribute("aria-label", label); }
        else { node.removeAttribute("title"); node.removeAttribute("aria-label"); }
      }
    }
    const select = (event: MouseEvent | KeyboardEvent) => {
      if (!paragraphSelectionEnabled || !onParagraphSelect) return;
      if (event instanceof KeyboardEvent && event.key !== "Enter" && event.key !== " ") return;
      const node = (event.target as HTMLElement).closest<HTMLElement>("[data-paragraph-index]");
      if (!node || !container.contains(node)) return;
      event.preventDefault();
      event.stopPropagation();
      const index = Number(node.dataset.paragraphIndex);
      const text = nodes.filter(p => Number(p.dataset.paragraphIndex) === index).map(p => p.textContent ?? "").join(" ").replace(/\s+/g, " ").trim().slice(0, 300);
      onParagraphSelect({ index, text });
    };
    container.addEventListener("click", select, true);
    container.addEventListener("keydown", select, true);
    return () => {
      container.removeEventListener("click", select, true);
      container.removeEventListener("keydown", select, true);
    };
  }, [pages, building, findings, paragraphTypes, selectedParagraphIndex, paragraphSelectionEnabled, onParagraphSelect, t]);

  return <>
    <div className="pf-docx-pagination-note" role="status">
      {building ? t("paginatingPreview") : failed ? t("paginationFailed") : t("previewPageCount", { count: pages.length })}
      <span>{t("previewPaginationHint")}</span>
    </div>
    <div className="pf-docx-scroll" aria-busy={building}>
      <div ref={root} className="pf-docx-pages" style={{ visibility: building || failed ? "hidden" : "visible" }} />
    </div>
  </>;
}
