import { useState, type ComponentType, type SVGProps } from "react";
import type { Editor } from "@tiptap/react";
import {
  ArrowUturnLeftIcon, ArrowUturnRightIcon, BoldIcon, ItalicIcon, UnderlineIcon,
  Bars3BottomLeftIcon, Bars3Icon, Bars3BottomRightIcon, Bars3CenterLeftIcon,
  ListBulletIcon, TableCellsIcon, PhotoIcon, ScissorsIcon, CodeBracketSquareIcon,
} from "@heroicons/react/24/outline";
import type { VariableCatalogEntry } from "../../../types/document";

export function EditorToolbar({ editor, variableCatalog, allowVariableInsertion = true }: { editor: Editor; variableCatalog: VariableCatalogEntry[]; allowVariableInsertion?: boolean }) {
  const [showVariablePicker, setShowVariablePicker] = useState(false);

  const setAlignment = (alignment: "left" | "center" | "right" | "justify") => {
    const parent = editor.state.selection.$from.parent;
    const { blockId, styleName, styleOverride } = parent.attrs;
    editor.chain().focus().updateAttributes(parent.type.name, { blockId, styleName, styleOverride: { ...styleOverride, alignment } }).run();
  };

  return (
    <div className="mb-3 flex flex-wrap items-center gap-1 rounded-xl border border-[var(--color-border)] bg-[#fbfcff] p-1.5 shadow-[0_1px_2px_rgba(15,27,45,0.03)]">
      <ToolbarButton icon={ArrowUturnLeftIcon} label="Отменить" onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()} />
      <ToolbarButton icon={ArrowUturnRightIcon} label="Повторить" onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()} />
      <Divider />
      <ToolbarButton icon={BoldIcon} label="Жирный" onClick={() => editor.chain().focus().toggleBold().run()} active={editor.isActive("bold")} />
      <ToolbarButton icon={ItalicIcon} label="Курсив" onClick={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive("italic")} />
      <ToolbarButton icon={UnderlineIcon} label="Подчёркнутый" onClick={() => editor.chain().focus().toggleUnderline().run()} active={editor.isActive("underline")} />
      <Divider />
      <ToolbarButton icon={Bars3BottomLeftIcon} label="По левому краю" onClick={() => setAlignment("left")} />
      <ToolbarButton icon={Bars3CenterLeftIcon} label="По центру" onClick={() => setAlignment("center")} />
      <ToolbarButton icon={Bars3BottomRightIcon} label="По правому краю" onClick={() => setAlignment("right")} />
      <ToolbarButton icon={Bars3Icon} label="По ширине" onClick={() => setAlignment("justify")} />
      <Divider />
      <select
        value={editor.isActive("heading", { level: 1 }) ? "1" : editor.isActive("heading", { level: 2 }) ? "2" : editor.isActive("heading", { level: 3 }) ? "3" : "0"}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "0") editor.chain().focus().setNode("paragraph").run();
          else editor.chain().focus().setNode("heading", { level: Number(v) }).run();
        }}
        className="rounded-lg border border-[var(--color-border)] bg-white px-2 py-1.5 text-xs font-medium text-[var(--color-ink-soft)]"
        title="Стиль абзаца"
      >
        <option value="0">Обычный текст</option>
        <option value="1">Заголовок 1</option>
        <option value="2">Заголовок 2</option>
        <option value="3">Заголовок 3</option>
      </select>
      <Divider />
      <ToolbarButton icon={ListBulletIcon} label="Список" onClick={() => editor.chain().focus().toggleBulletList().run()} active={editor.isActive("bulletList")} />
      <ToolbarButton icon={TableCellsIcon} label="Таблица" onClick={() => editor.chain().focus().insertTable({ rows: 2, cols: 2, withHeaderRow: false }).run()} />
      <ToolbarButton icon={PhotoIcon} label="Изображение" onClick={() => editor.chain().focus().insertContent({ type: "pfImage" }).run()} />
      <ToolbarButton icon={ScissorsIcon} label="Разрыв страницы" onClick={() => editor.chain().focus().insertContent({ type: "pfPageBreak" }).run()} />
      {allowVariableInsertion && (
        <span className="relative">
          <ToolbarButton icon={CodeBracketSquareIcon} label="Вставить переменную" onClick={() => setShowVariablePicker((v) => !v)} />
          {showVariablePicker && (
            <div className="absolute left-0 top-10 z-20 max-h-56 w-56 overflow-y-auto rounded-xl border border-[var(--color-border)] bg-white p-1.5 shadow-[var(--shadow-float)]">
              {variableCatalog.map((v) => (
                <button
                  key={v.key}
                  type="button"
                  onClick={() => {
                    editor.chain().focus().insertContent({ type: "pfVariable", attrs: { key: v.key, label: v.label } }).run();
                    setShowVariablePicker(false);
                  }}
                  className="block w-full rounded-lg px-2.5 py-2 text-left text-xs font-medium text-[var(--color-ink-soft)] hover:bg-[var(--color-brand-50)] hover:text-[var(--color-brand-700)]"
                >
                  {v.label}
                </button>
              ))}
            </div>
          )}
        </span>
      )}
    </div>
  );
}

function Divider() {
  return <span className="mx-0.5 h-5 w-px bg-[var(--color-border)]" />;
}

function ToolbarButton({
  icon,
  label,
  onClick,
  active,
  disabled,
}: {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg p-1.5 transition-colors ${active ? "bg-[var(--color-brand-50)] text-[var(--color-brand-700)]" : "text-[var(--color-ink-soft)] hover:bg-[var(--color-surface)]"} disabled:opacity-30`}
    >
      {(() => { const Icon = icon; return <Icon className="size-4" aria-hidden="true" />; })()}
    </button>
  );
}
