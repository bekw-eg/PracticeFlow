import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { DocumentConflictNotice } from "../documentConflict";
import { useDocumentAutosave } from "../documentAutosave";

const staleRevisionError = {
  response: {
    status: 409,
    data: { detail: { code: "STALE_DOCUMENT_REVISION" } },
  },
};

function AutosaveHarness({ save, onRefresh, onCopy }: { save: (document: string, expectedRevision: number) => Promise<{ revision: number }>; onRefresh: () => void; onCopy: () => void }) {
  const [hasConflict, setHasConflict] = useState(false);
  const { queueSave, reset } = useDocumentAutosave({
    delayMs: 0,
    save,
    onSaved: vi.fn(),
    onConflict: () => setHasConflict(true),
  });

  useEffect(() => {
    reset(1);
  }, [reset]);

  return (
    <>
      <button type="button" onClick={() => queueSave("local draft")}>Изменить документ</button>
      {hasConflict && <DocumentConflictNotice onRefresh={onRefresh} onCopy={onCopy} copyState="idle" />}
    </>
  );
}

describe("document optimistic-lock conflict UI", () => {
  it("stops further autosaves and exposes refresh/copy actions after a 409 stale-revision response", async () => {
    const save = vi.fn<(document: string, expectedRevision: number) => Promise<{ revision: number }>>().mockRejectedValue(staleRevisionError);
    const onRefresh = vi.fn();
    const onCopy = vi.fn();

    render(<AutosaveHarness save={save} onRefresh={onRefresh} onCopy={onCopy} />);
    fireEvent.click(screen.getByRole("button", { name: "Изменить документ" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Документ был изменён в другой вкладке");
    expect(save).toHaveBeenCalledWith("local draft", 1);

    fireEvent.click(screen.getByRole("button", { name: "Изменить документ" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Обновить данные" }));
    fireEvent.click(screen.getByRole("button", { name: "Скопировать несохранённые изменения" }));
    expect(onRefresh).toHaveBeenCalledOnce();
    expect(onCopy).toHaveBeenCalledOnce();
  });
});
