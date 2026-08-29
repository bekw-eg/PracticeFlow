import { useContext } from "react";

import { NumberingContext } from "./numberingContextValue";

export function useNumbering(blockId: string | null): string | undefined {
  const numbering = useContext(NumberingContext);
  return blockId ? numbering[blockId] : undefined;
}
