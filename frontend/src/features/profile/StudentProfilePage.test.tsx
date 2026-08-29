import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import { StudentProfilePage } from "./StudentProfilePage";

vi.mock("../../lib/api", () => ({
  api: { get: vi.fn(), patch: vi.fn() },
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><StudentProfilePage /></QueryClientProvider>);
}

describe("StudentProfilePage API failure", () => {
  beforeEach(() => vi.clearAllMocks());

  it("replaces the former infinite loading state with a 404 alert and manual retry", async () => {
    vi.mocked(api.get).mockRejectedValue({ response: { status: 404 } });

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Данные не найдены");
    expect(screen.queryByText("Загрузка профиля…")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });
});
