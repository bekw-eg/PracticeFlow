import type { Block, DocumentMeta } from "../../types/document";
import { AuthenticatedImage } from "../../components/AuthenticatedImage";
import { resolveStyle } from "./resolveStyle";
import { RunView } from "./RunView";

export function BlockView({ block, meta, numberPrefix }: { block: Block; meta: DocumentMeta; numberPrefix?: string }) {
  switch (block.type) {
    case "paragraph":
      return (
        <p style={resolveStyle(meta, block)}>
          {block.runs.map((run) => (
            <RunView key={run.id} run={run} />
          ))}
        </p>
      );
    case "heading":
      return (
        <p style={resolveStyle(meta, block)}>
          {numberPrefix && <span className="mr-2 text-[var(--color-muted)]">{numberPrefix}</span>}
          {block.runs.map((run) => (
            <RunView key={run.id} run={run} />
          ))}
        </p>
      );
    case "image":
      return (
        <figure className="my-3" style={{ textAlign: block.alignment }}>
          {block.file_id ? (
            <AuthenticatedImage
              fileId={block.file_id}
              alt={block.caption}
              style={{ width: block.width_mm ? `${block.width_mm}mm` : "auto", display: "inline-block" }}
            />
          ) : (
            <div className="inline-flex h-32 w-48 items-center justify-center rounded border border-dashed border-[var(--color-border)] text-xs text-[var(--color-muted)]">
              Нет изображения
            </div>
          )}
          {block.caption && <figcaption className="mt-1 text-xs text-[var(--color-muted)]">{block.caption}</figcaption>}
        </figure>
      );
    case "table":
      return (
        <table className="my-3 w-full border-collapse border border-[var(--color-border)] text-sm">
          <tbody>
            {block.rows.map((row) => (
              <tr key={row.id}>
                {row.cells.map((cell) => (
                  <td key={cell.id} className="border border-[var(--color-border)] p-2 align-top">
                    {cell.blocks.map((b) => (
                      <BlockView key={b.id} block={b} meta={meta} />
                    ))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      );
    case "list":
      return block.ordered ? (
        <ol className="my-2 list-decimal pl-6">
          {block.items.map((item) => (
            <li key={item.id}>
              {item.blocks.map((b) => (
                <BlockView key={b.id} block={b} meta={meta} />
              ))}
            </li>
          ))}
        </ol>
      ) : (
        <ul className="my-2 list-disc pl-6">
          {block.items.map((item) => (
            <li key={item.id}>
              {item.blocks.map((b) => (
                <BlockView key={b.id} block={b} meta={meta} />
              ))}
            </li>
          ))}
        </ul>
      );
    case "pageBreak":
      return (
        <div className="my-4 flex items-center gap-2 text-xs text-[var(--color-muted)]">
          <span className="h-px flex-1 bg-[var(--color-border)]" />
          разрыв страницы
          <span className="h-px flex-1 bg-[var(--color-border)]" />
        </div>
      );
  }
}
