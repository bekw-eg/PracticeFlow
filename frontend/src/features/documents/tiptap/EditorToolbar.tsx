import { useState, type ComponentType, type SVGProps } from "react";
import type { Editor } from "@tiptap/react";
import {
  ArrowUturnLeftIcon, ArrowUturnRightIcon, BoldIcon, ItalicIcon, UnderlineIcon,
  Bars3BottomLeftIcon, Bars3Icon, Bars3BottomRightIcon, Bars3CenterLeftIcon,
  ListBulletIcon, TableCellsIcon, PhotoIcon, ScissorsIcon, CodeBracketSquareIcon,
} from "@heroicons/react/24/outline";
import type { VariableCatalogEntry } from "../../../types/document";
import { useTranslation } from "react-i18next";

export function EditorToolbar({ editor, variableCatalog, allowVariableInsertion = true }: { editor: Editor; variableCatalog: VariableCatalogEntry[]; allowVariableInsertion?: boolean }) {
  const { t } = useTranslation("editor");
  const [showVariablePicker, setShowVariablePicker] = useState(false);

  const setAlignment = (alignment: "left" | "center" | "right" | "justify") => {
    const parent = editor.state.selection.$from.parent;
    const { blockId, styleName, styleOverride } = parent.attrs;
    editor.chain().focus().updateAttributes(parent.type.name, { blockId, styleName, styleOverride: { ...styleOverride, alignment } }).run();
  };

  return (
    <div
      role="toolbar"
      aria-label={t("toolbar")}
      className="mb-3 flex flex-wrap items-center gap-1 rounded-[6px] border border-[var(--color-border)] bg-[#f7f6f2] p-1.5"
    >
      <ToolbarButton icon={ArrowUturnLeftIcon} label={t("undo")} onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()} />
      <ToolbarButton icon={ArrowUturnRightIcon} label={t("redo")} onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()} />
      <Divider />
      <ToolbarButton icon={BoldIcon} label={t("bold")} onClick={() => editor.chain().focus().toggleBold().run()} active={editor.isActive("bold")} />
      <ToolbarButton icon={ItalicIcon} label={t("italic")} onClick={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive("italic")} />
      <ToolbarButton icon={UnderlineIcon} label={t("underline")} onClick={() => editor.chain().focus().toggleUnderline().run()} active={editor.isActive("underline")} />
      <Divider />
      <ToolbarButton icon={Bars3BottomLeftIcon} label={t("alignLeft")} onClick={() => setAlignment("left")} />
      <ToolbarButton icon={Bars3CenterLeftIcon} label={t("alignCenter")} onClick={() => setAlignment("center")} />
      <ToolbarButton icon={Bars3BottomRightIcon} label={t("alignRight")} onClick={() => setAlignment("right")} />
      <ToolbarButton icon={Bars3Icon} label={t("alignJustify")} onClick={() => setAlignment("justify")} />
      <Divider />
      <select
        value={editor.isActive("heading", { level: 1 }) ? "1" : editor.isActive("heading", { level: 2 }) ? "2" : editor.isActive("heading", { level: 3 }) ? "3" : "0"}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "0") editor.chain().focus().setNode("paragraph").run();
          else editor.chain().focus().setNode("heading", { level: Number(v) }).run();
        }}
        aria-label={t("paragraphStyle")}
        className="rounded-[5px] border border-[var(--color-border)] bg-white px-2 py-1.5 text-xs font-medium text-[var(--color-ink-soft)]"
        title={t("paragraphStyle")}
      >
        <option value="0">{t("normalText")}</option>
        <option value="1">{t("heading1")}</option>
        <option value="2">{t("heading2")}</option>
        <option value="3">{t("heading3")}</option>
      </select>
      <Divider />
      <ToolbarButton icon={ListBulletIcon} label={t("bulletList")} onClick={() => editor.chain().focus().toggleBulletList().run()} active={editor.isActive("bulletList")} />
      <ToolbarButton icon={TableCellsIcon} label={t("table")} onClick={() => editor.chain().focus().insertTable({ rows: 2, cols: 2, withHeaderRow: false }).run()} />
      <ToolbarButton icon={PhotoIcon} label={t("image")} onClick={() => editor.chain().focus().insertContent({ type: "pfImage" }).run()} />
      <ToolbarButton icon={ScissorsIcon} label={t("pageBreak")} onClick={() => editor.chain().focus().insertContent({ type: "pfPageBreak" }).run()} />
      {allowVariableInsertion && (
        <span className="relative">
          <ToolbarButton icon={CodeBracketSquareIcon} label={t("insertVariable")} onClick={() => setShowVariablePicker((v) => !v)} />
          {showVariablePicker && (
            <div
              role="group"
              aria-label={t("variablePicker")}
              className="absolute left-0 top-10 z-20 max-h-56 w-56 overflow-y-auto rounded-lg border border-[var(--color-border)] bg-white p-1.5 shadow-[var(--shadow-float)]"
            >
              {variableCatalog.map((v) => (
                <button
                  key={v.key}
                  type="button"
                  onClick={() => {
                    editor.chain().focus().insertContent({ type: "pfVariable", attrs: { key: v.key, label: v.label } }).run();
                    setShowVariablePicker(false);
                  }}
                  className="block w-full rounded-[5px] px-2.5 py-2 text-left text-xs font-medium text-[var(--color-ink-soft)] hover:bg-[var(--color-brand-50)] hover:text-[var(--color-brand-700)]"
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
      className={`rounded-[4px] p-1.5 transition-colors ${active ? "bg-[var(--color-brand-100)] text-[var(--color-brand-700)]" : "text-[var(--color-ink-soft)] hover:bg-white"} disabled:opacity-30`}
    >
      {(() => { const Icon = icon; return <Icon className="size-4" aria-hidden="true" />; })()}
    </button>
  );
}
