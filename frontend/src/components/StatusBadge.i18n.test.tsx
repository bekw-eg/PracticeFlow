import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { changeLocale } from "../i18n";
import { StatusBadge } from "./StatusBadge";

const localeCases = [
  { locale: "ru" as const, status: "Черновик", unknown: "Неизвестный статус" },
  { locale: "kk" as const, status: "Жоба", unknown: "Белгісіз күй" },
  { locale: "en" as const, status: "Draft", unknown: "Unknown status" },
];

describe("StatusBadge i18n", () => {
  afterEach(async () => {
    await changeLocale("ru");
  });

  it.each(localeCases)("localizes known and unknown statuses for $locale", async ({ locale, status, unknown }) => {
    await changeLocale(locale);
    const { rerender } = render(<StatusBadge status="DRAFT" />);

    expect(screen.getByLabelText(status)).toHaveTextContent(status);

    rerender(<StatusBadge status="UNSUPPORTED_STATUS" />);
    expect(screen.getByLabelText(unknown)).toHaveTextContent(unknown);
    expect(screen.queryByText("UNSUPPORTED_STATUS")).not.toBeInTheDocument();
  });
});
