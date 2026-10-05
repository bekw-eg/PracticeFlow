import type { NotificationOut } from "../types/api";

type NotificationTranslationKey =
  | "notificationTypes.PRACTICE_ASSIGNED"
  | "notificationTypes.REPORT_SUBMITTED"
  | "notificationTypes.REVISION_REQUIRED"
  | "notificationTypes.REPORT_COMMENT"
  | "notificationTypes.COMMENT_REPLY"
  | "notificationTypes.REPORT_DEADLINE_SOON"
  | "notificationTypes.REPORT_DEADLINE_TODAY"
  | "notificationTypes.REPORT_DEADLINE_OVERDUE"
  | "notificationTypes.DOCUMENT_CHECK_ASSIGNED"
  | "notificationTypes.UNKNOWN"
  | "notificationBodies.REPORT_SUBMITTED"
  | "notificationBodies.REVISION_REQUIRED";

type Translate = (key: NotificationTranslationKey) => string;

const titleKeys: Record<string, NotificationTranslationKey> = {
  PRACTICE_ASSIGNED: "notificationTypes.PRACTICE_ASSIGNED",
  REPORT_SUBMITTED: "notificationTypes.REPORT_SUBMITTED",
  REVISION_REQUIRED: "notificationTypes.REVISION_REQUIRED",
  REPORT_COMMENT: "notificationTypes.REPORT_COMMENT",
  COMMENT_REPLY: "notificationTypes.COMMENT_REPLY",
  REPORT_DEADLINE_SOON: "notificationTypes.REPORT_DEADLINE_SOON",
  REPORT_DEADLINE_TODAY: "notificationTypes.REPORT_DEADLINE_TODAY",
  REPORT_DEADLINE_OVERDUE: "notificationTypes.REPORT_DEADLINE_OVERDUE",
  DOCUMENT_CHECK_ASSIGNED: "notificationTypes.DOCUMENT_CHECK_ASSIGNED",
};

const generatedBodyKeys: Record<string, NotificationTranslationKey> = {
  "Студент отправил отчёт по практике.": "notificationBodies.REPORT_SUBMITTED",
  "Преподаватель запросил доработку отчёта.": "notificationBodies.REVISION_REQUIRED",
};

/**
 * Notification titles in older rows are server-generated Russian text. The
 * type is stable, so rendering from it localizes the UI without modifying
 * persisted notifications. Bodies are retained when they may be author text
 * (comments, internship names, and review notes).
 */
export function notificationTitle(notification: Pick<NotificationOut, "type">, t: Translate): string {
  const key = titleKeys[notification.type];
  return key ? t(key) : t("notificationTypes.UNKNOWN");
}

export function notificationBody(notification: Pick<NotificationOut, "body">, t: Translate): string | null {
  if (!notification.body) return null;
  return generatedBodyKeys[notification.body] ? t(generatedBodyKeys[notification.body]) : notification.body;
}
