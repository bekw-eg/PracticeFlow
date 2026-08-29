import type { ReactNode } from "react";

import { NumberingContext } from "./numberingContextValue";

/**
 * Server-computed numbering (app/documents/numbering.py) is the ONE
 * authoritative source (Phase 2.5 fix — Phase 2 had a duplicate TS
 * reimplementation that could drift from the backend). This context is how
 * that map reaches the Heading/Section NodeViews inside a live Tiptap
 * editor without forcing a full editor remount on every save response.
 */
export function NumberingProvider({ value, children }: { value: Record<string, string>; children: ReactNode }) {
  return <NumberingContext.Provider value={value}>{children}</NumberingContext.Provider>;
}
