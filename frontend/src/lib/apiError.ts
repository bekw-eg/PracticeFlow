import { isAxiosError } from "axios";

export type ApiErrorKind = "payload-too-large" | "forbidden" | "not-found" | "conflict" | "rate-limited" | "server" | "network" | "unauthorized" | "unknown";

export interface ApiErrorPresentation {
  kind: ApiErrorKind;
  title: string;
  description: string;
  status: number | null;
}

type ErrorLike = {
  response?: { status?: unknown };
  status?: unknown;
  request?: unknown;
  code?: unknown;
};

function statusFrom(error: unknown): number | null {
  if (isAxiosError(error)) return typeof error.response?.status === "number" ? error.response.status : null;
  if (typeof error === "object" && error !== null) {
    const candidate = error as ErrorLike;
    if (typeof candidate.response?.status === "number") return candidate.response.status;
    if (typeof candidate.status === "number") return candidate.status;
  }
  return null;
}

function isNetworkError(error: unknown): boolean {
  if (isAxiosError(error)) return !error.response && Boolean(error.request || error.code === "ERR_NETWORK");
  if (typeof error === "object" && error !== null) {
    const candidate = error as ErrorLike;
    return !candidate.response && Boolean(candidate.request || candidate.code === "ERR_NETWORK");
  }
  return false;
}

export function getApiErrorPresentation(error: unknown): ApiErrorPresentation {
  const status = statusFrom(error);

  switch (status) {
    case 413:
      return { kind: "payload-too-large", status, title: "Файл слишком большой", description: "Выберите изображение меньшего размера и повторите загрузку." };
    case 401:
      return { kind: "unauthorized", status, title: "Сеанс завершён", description: "Войдите в систему снова, чтобы продолжить работу." };
    case 403:
      return { kind: "forbidden", status, title: "Доступ запрещён", description: "У вас нет прав для просмотра этих данных или выполнения этого действия." };
    case 404:
      return { kind: "not-found", status, title: "Данные не найдены", description: "Возможно, объект был удалён, ссылка устарела или он недоступен в текущей организации." };
    case 409:
      return { kind: "conflict", status, title: "Обнаружен конфликт данных", description: "Данные изменились в другом окне или другим пользователем. Обновите данные и повторите действие." };
    case 429:
      return { kind: "rate-limited", status, title: "Слишком много запросов", description: "Подождите немного и повторите попытку." };
    default:
      if (status !== null && status >= 500) {
        return { kind: "server", status, title: "Ошибка сервера", description: "Сервис временно недоступен. Повторите попытку позже." };
      }
      if (isNetworkError(error)) {
        return { kind: "network", status: null, title: "Нет соединения с сервером", description: "Проверьте подключение к интернету или VPN и повторите попытку." };
      }
      return { kind: "unknown", status, title: "Не удалось выполнить запрос", description: "Попробуйте повторить попытку. Если проблема сохранится, обратитесь к администратору." };
  }
}

/**
 * Authorization, missing-resource and conflict responses are deterministic;
 * retrying them automatically only creates duplicate requests. Transient
 * failures get one bounded retry, while the UI always keeps a manual retry.
 */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  const { status } = getApiErrorPresentation(error);
  return failureCount < 1 && ![401, 403, 404, 409].includes(status ?? -1);
}
