import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SaveStatus } from "../SaveStatus";

describe("SaveStatus", () => {
  it("renders nothing for idle", () => {
    const { container } = render(<SaveStatus state="idle" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows saving state", () => {
    render(<SaveStatus state="saving" />);
    expect(screen.getByText(/Сохранение/)).toBeInTheDocument();
  });

  it("shows saved state", () => {
    render(<SaveStatus state="saved" />);
    expect(screen.getByText(/Сохранено/)).toBeInTheDocument();
  });

  it("shows error state with an explicit warning that changes are unsaved", () => {
    render(<SaveStatus state="error" />);
    expect(screen.getByText(/Ошибка сохранения/)).toBeInTheDocument();
    expect(screen.getByText(/несохранённые изменения/)).toBeInTheDocument();
  });
});
