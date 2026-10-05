import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import { CreateInternshipDialog } from "./CreateInternshipDialog";

const templatesResponse = {
  data: [{
    id: "template-1",
    name: "Шаблон практики",
    description: null,
    versions: [{ id: "version-1", version_number: 1, is_published: true, is_locked: false, created_at: "2026-01-01T00:00:00Z" }],
  }],
  headers: { "x-total-count": "1", "x-offset": "0", "x-limit": "25", "x-has-more": "false" },
} as never;

function renderDialog(onClose = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><CreateInternshipDialog groupId="group-1" onClose={onClose} /></QueryClientProvider>);
  return onClose;
}

function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText("Название"), { target: { value: "Летняя практика" } });
  fireEvent.change(screen.getByLabelText("Шаблон (версия)"), { target: { value: "version-1" } });
  fireEvent.change(screen.getByLabelText("Начало"), { target: { value: "2026-06-01" } });
  fireEvent.change(screen.getByLabelText("Конец"), { target: { value: "2026-07-15" } });
  fireEvent.change(screen.getByLabelText("Дедлайн"), { target: { value: "2026-07-20" } });
}

afterEach(() => vi.restoreAllMocks());

describe("CreateInternshipDialog description", () => {
  it("sends student instructions with the current create request", async () => {
    vi.spyOn(api, "get").mockResolvedValue(templatesResponse);
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { id: "internship-1" } } as never);
    const onClose = renderDialog();

    const description = await screen.findByLabelText("Описание / инструкции для студентов");
    expect(description).toHaveAttribute("maxlength", "2000");
    expect(screen.getByText("Студенты увидят это вместе с назначенной практикой. Текст не станет частью их отчёта.")).toBeInTheDocument();
    fireEvent.change(description, { target: { value: "Подготовьте дневник и приложите отзыв руководителя." } });
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() => expect(post).toHaveBeenCalledWith("/groups/group-1/internships", {
      title: "Летняя практика",
      description: "Подготовьте дневник и приложите отзыв руководителя.",
      template_version_id: "version-1",
      start_date: "2026-06-01",
      end_date: "2026-07-15",
      deadline: "2026-07-20",
    }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("keeps the dialog open and displays a validation error", async () => {
    vi.spyOn(api, "get").mockResolvedValue(templatesResponse);
    vi.spyOn(api, "post").mockRejectedValue({
      response: { status: 422, data: { detail: [{ loc: ["body", "description"], type: "string_too_long" }] } },
    });
    const onClose = renderDialog();

    await screen.findByLabelText("Описание / инструкции для студентов");
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent("Не удалось создать практику. Проверьте заполненные поля.");
    expect(onClose).not.toHaveBeenCalled();
  });
});
