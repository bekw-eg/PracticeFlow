import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { SectionEditor } from "../SectionEditor";
import type { DocumentMeta, Section } from "../../../types/document";

const meta: DocumentMeta = {
  page_size: "A4",
  orientation: "portrait",
  margins: { top_mm: 20, bottom_mm: 20, left_mm: 30, right_mm: 10 },
  default_font: "Times New Roman",
  default_font_size: 14,
  line_spacing: 1.5,
  styles: {},
  numbering: { enabled: true, start_number: 1, style: "decimal" },
};

function lockedSection(): Section {
  return {
    id: "sec_locked",
    key: "intro",
    title: "Введение",
    level: 1,
    required: true,
    editable: false,
    page_break_before: false,
    numbering: { participates: true },
    blocks: [{ type: "paragraph", id: "p_1", style_name: "Normal", style_override: null, runs: [{ kind: "text", id: "r_1", text: "Locked content", bold: false, italic: false, underline: false }] }],
  };
}

function editableSection(): Section {
  return {
    id: "sec_editable",
    key: "ch1",
    title: "Глава 1",
    level: 1,
    required: true,
    editable: true,
    page_break_before: false,
    numbering: { participates: true },
    blocks: [{ type: "paragraph", id: "p_2", style_name: "Normal", style_override: null, runs: [{ kind: "text", id: "r_2", text: "Editable content", bold: false, italic: false, underline: false }] }],
  };
}

describe("SectionEditor: locked vs editable boundary", () => {
  it("renders a locked section as plain read-only text with NO contenteditable surface at all", async () => {
    const { container } = await act(async () =>
      render(
        <SectionEditor section={lockedSection()} numbering={{}} meta={meta} variableCatalog={[]} canEdit={true} onBlocksChange={vi.fn()} />
      )
    );
    expect(screen.getByText("Locked content")).toBeInTheDocument();
    // Critical safety property: a locked section must not even HAVE an
    // editable surface — not "editable but rejected on save", genuinely
    // absent, matching the backend's structural enforcement.
    expect(container.querySelector('[contenteditable="true"]')).toBeNull();
    expect(container.querySelector(".ProseMirror")).toBeNull();
    expect(screen.queryByTitle("Жирный")).not.toBeInTheDocument(); // no toolbar
  });

  it("renders an editable section with a real editable ProseMirror surface and toolbar", async () => {
    const { container } = await act(async () =>
      render(
        <SectionEditor section={editableSection()} numbering={{}} meta={meta} variableCatalog={[]} canEdit={true} onBlocksChange={vi.fn()} />
      )
    );
    expect(screen.getByText("Editable content")).toBeInTheDocument();
    expect(container.querySelector('[contenteditable="true"]')).not.toBeNull();
    expect(screen.getByTitle("Жирный")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Редактор раздела: Глава 1" })).toBeInTheDocument();
  });

  it("does not expose the teacher-only variable picker in a student report editor", async () => {
    await act(async () =>
      render(
        <SectionEditor
          section={editableSection()}
          numbering={{}}
          meta={meta}
          variableCatalog={[]}
          allowVariableInsertion={false}
          canEdit
          onBlocksChange={vi.fn()}
        />
      )
    );

    expect(screen.queryByRole("button", { name: "Вставить переменную" })).not.toBeInTheDocument();
  });

  it("locks an otherwise-editable section when the DOCUMENT is read-only (canEdit=false) — e.g. teacher viewing a submitted report", async () => {
    const { container } = await act(async () =>
      render(
        <SectionEditor section={editableSection()} numbering={{}} meta={meta} variableCatalog={[]} canEdit={false} onBlocksChange={vi.fn()} />
      )
    );
    expect(screen.getByText("Editable content")).toBeInTheDocument();
    expect(container.querySelector('[contenteditable="true"]')).toBeNull();
  });

  it("shows a visible lock indicator for locked sections so the boundary is understandable to students, not just backend-enforced", async () => {
    await act(async () =>
      render(
        <SectionEditor section={lockedSection()} numbering={{}} meta={meta} variableCatalog={[]} canEdit={true} onBlocksChange={vi.fn()} />
      )
    );
    expect(screen.getByText(/закреплено преподавателем/i)).toBeInTheDocument();
  });

  it("lets a teacher edit a section title even when that section is locked for students", async () => {
    const onTitleChange = vi.fn();
    await act(async () =>
      render(
        <SectionEditor
          section={lockedSection()}
          numbering={{}}
          meta={meta}
          variableCatalog={[]}
          canEdit={false}
          canEditTitle
          onTitleChange={onTitleChange}
          onBlocksChange={vi.fn()}
        />
      )
    );

    fireEvent.change(screen.getByRole("textbox", { name: "Название раздела" }), { target: { value: "Новая глава" } });
    expect(onTitleChange).toHaveBeenCalledWith("Новая глава");
    expect(screen.queryByText("Locked content")).toBeInTheDocument();
  });

  it("does not expose a title input to students", async () => {
    await act(async () =>
      render(<SectionEditor section={editableSection()} numbering={{}} meta={meta} variableCatalog={[]} canEdit onBlocksChange={vi.fn()} />)
    );
    expect(screen.queryByRole("textbox", { name: "Название раздела" })).toBeNull();
  });
});
