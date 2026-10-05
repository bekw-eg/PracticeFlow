import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "../../components/ui/StateViews";
import { useProductFeatures } from "../auth/useProductFeatures";

export function DocumentChecksGate({ children }: { children: ReactNode }) {
  const { document_check_enabled } = useProductFeatures();
  const { t } = useTranslation("documentChecks");
  return document_check_enabled ? children : <EmptyState title={t("featureUnavailable")} />;
}
