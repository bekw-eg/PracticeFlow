import type { NotificationOut } from "../types/api";

type NotificationTranslationKey =
  | "notificationTypes.DOCUMENT_CHECK_ASSIGNED"
  | "notificationTypes.UNKNOWN";

type Translate = (key: NotificationTranslationKey) => string;

const titleKeys: Record<string, NotificationTranslationKey> = {
  DOCUMENT_CHECK_ASSIGNED: "notificationTypes.DOCUMENT_CHECK_ASSIGNED",
};

/**
 * Notification titles are localized from stable notification types rather than
 * persisted server strings. Bodies are retained verbatim when present.
 */
export function notificationTitle(notification: Pick<NotificationOut, "type">, t: Translate): string {
  const key = titleKeys[notification.type];
  return key ? t(key) : t("notificationTypes.UNKNOWN");
}

export function notificationBody(notification: Pick<NotificationOut, "body">): string | null {
  return notification.body || null;
}
