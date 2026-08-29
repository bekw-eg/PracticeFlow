import { getApiErrorPresentation } from "./apiError";

export function uploadErrorMessage(error: unknown): string {
  const presentation = getApiErrorPresentation(error);
  if (presentation.status === 413) return "Изображение слишком большое. Выберите файл меньшего размера.";
  if (presentation.status === 429) return "Лимит загрузок исчерпан. Подождите немного и повторите попытку.";
  return "Не удалось загрузить изображение. Повторите попытку позже.";
}

export function exportErrorMessage(error: unknown): string {
  const presentation = getApiErrorPresentation(error);
  if (presentation.status === 429) return "Слишком много запросов на экспорт. Подождите немного и повторите попытку.";
  return "Не удалось сформировать файл. Повторите попытку позже.";
}
