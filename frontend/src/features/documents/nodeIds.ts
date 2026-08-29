// Mirrors backend/app/documents/node_ids.py — same shape, same guarantee
// (stable, non-index identity for every node created client-side).
export function newNodeId(prefix: string): string {
  const random = Math.random().toString(16).slice(2, 10).padEnd(8, "0");
  return `${prefix}_${random}`;
}
