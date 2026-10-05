import { describe, expect, it } from "vitest";

import { exportErrorMessage, uploadErrorMessage } from "./resourceErrorMessages";

describe("resource protection error messages", () => {
  it("explains the file-size and upload-quota responses without backend details", () => {
    expect(uploadErrorMessage({ response: { status: 413 } })).toBe("Изображение слишком большое. Выберите файл меньшего размера.");
    expect(uploadErrorMessage({ response: { status: 429 } })).toBe("Лимит загрузок исчерпан. Подождите немного и повторите попытку.");
  });

  it("explains export throttling without exposing implementation details", () => {
    expect(exportErrorMessage({ response: { status: 429 } })).toBe("Слишком много запросов на экспорт. Подождите немного и повторите попытку.");
    expect(exportErrorMessage({ response: { status: 504 } })).toBe("Экспорт временно недоступен. Повторите попытку позже.");
  });
});
