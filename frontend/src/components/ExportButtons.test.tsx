import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { ExportButtons } from "./ExportButtons";

vi.mock("../lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const mockedGet = vi.mocked(api.get);
const mockedPost = vi.mocked(api.post);

describe("ExportButtons", () => {
  it("polls an accepted job, exposes a download and prevents duplicate job creation", async () => {
    mockedPost.mockResolvedValueOnce({ data: { job_id: "job-1", status: "queued" } });
    mockedGet.mockResolvedValueOnce({ data: { status: "succeeded", download_url: "/export-jobs/job-1/download" } });
    mockedGet.mockResolvedValueOnce({ data: new Blob(["file"]), headers: {} });
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:report"), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    render(<ExportButtons reportId="report-1" />);
    fireEvent.click(screen.getByRole("button", { name: "DOCX" }));
    fireEvent.click(screen.getByRole("button", { name: "PDF" }));
    expect(mockedPost).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("status")).toHaveTextContent("Экспорт готовится");
    const downloadButton = await screen.findByRole("button", { name: "Скачать DOCX" });
    fireEvent.click(downloadButton);
    await waitFor(() => expect(mockedGet).toHaveBeenCalledWith("/export-jobs/job-1/download", { responseType: "blob" }));
  });

  it("shows a friendly 429 creation error", async () => {
    mockedPost.mockRejectedValueOnce({ response: { status: 429 } });
    render(<ExportButtons reportId="report-1" />);
    fireEvent.click(screen.getByRole("button", { name: "DOCX" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Слишком много запросов на экспорт");
  });
});
