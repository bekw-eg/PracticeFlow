import { useContext } from "react";

import type { ProductFeatures } from "../../types/api";
import { AuthContext } from "./authContextValue";

const DEFAULT_PRODUCT_FEATURES: ProductFeatures = {
  document_check_enabled: true,
  legacy_document_editor_enabled: true,
};

export function useProductFeatures(): ProductFeatures {
  return useContext(AuthContext)?.user?.features ?? DEFAULT_PRODUCT_FEATURES;
}
