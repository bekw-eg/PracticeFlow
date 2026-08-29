import { PhotoIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import { NodeViewWrapper, type NodeViewProps } from "@tiptap/react";
import { useRef, useState } from "react";

import { AuthenticatedImage } from "../../../components/AuthenticatedImage";
import { uploadErrorMessage } from "../../../lib/resourceErrorMessages";
import { uploadImage } from "../api";

export function ImageNodeView({ node, updateAttributes, editor }: NodeViewProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const editable = editor.isEditable;

  const handleFile = async (file: File) => {
    if (isUploading) return;
    setUploadError(null);
    setIsUploading(true);
    try {
      const uploaded = await uploadImage(file);
      updateAttributes({ fileId: uploaded.id });
    } catch (error) {
      setUploadError(uploadErrorMessage(error));
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <NodeViewWrapper className="pf-image-node my-2" style={{ textAlign: node.attrs.alignment }}>
      {node.attrs.fileId ? (
        <figure className="inline-block" contentEditable={false}>
          <AuthenticatedImage
            fileId={node.attrs.fileId}
            alt={node.attrs.caption}
            style={{ width: `${node.attrs.widthMm}mm`, display: "inline-block" }}
          />
          {editable ? (
            <input
              value={node.attrs.caption}
              onChange={(event) => updateAttributes({ caption: event.target.value })}
              placeholder="Подпись к изображению"
              className="input mt-1 block text-xs"
            />
          ) : (
            node.attrs.caption && <figcaption className="mt-1 text-xs text-[var(--color-muted)]">{node.attrs.caption}</figcaption>
          )}
          {editable && (
            <div className="mt-1 flex items-center gap-2 text-xs">
              <select
                value={node.attrs.alignment}
                onChange={(event) => updateAttributes({ alignment: event.target.value })}
                className="rounded border border-[var(--color-border)] bg-white px-1 py-0.5"
              >
                <option value="left">Слева</option>
                <option value="center">По центру</option>
                <option value="right">Справа</option>
              </select>
              <input
                type="range"
                min={30}
                max={170}
                value={node.attrs.widthMm}
                onChange={(event) => updateAttributes({ widthMm: Number(event.target.value) })}
              />
              <button type="button" onClick={() => inputRef.current?.click()} className="text-[var(--color-brand-600)]">
                Заменить
              </button>
            </div>
          )}
        </figure>
      ) : (
        <button
          type="button"
          contentEditable={false}
          onClick={() => inputRef.current?.click()}
          disabled={isUploading || !editable}
          className="flex h-28 w-40 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-[var(--color-border)] text-[var(--color-muted)] transition-colors hover:border-[var(--color-brand-500)] hover:bg-[var(--color-brand-50)] hover:text-[var(--color-brand-600)]"
        >
          {isUploading ? <ArrowPathIcon className="size-[22px] animate-spin" /> : <PhotoIcon className="size-[22px]" />}
          <span className="text-xs">{isUploading ? "Загрузка…" : "Загрузить изображение"}</span>
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(event) => event.target.files?.[0] && handleFile(event.target.files[0])}
      />
      {uploadError && <p role="alert" className="mt-2 text-xs text-[var(--color-danger-500)]">{uploadError}</p>}
    </NodeViewWrapper>
  );
}
