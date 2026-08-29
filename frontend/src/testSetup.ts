import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// jsdom implements no real layout engine, so it has no geometry APIs.
// ProseMirror's view layer calls these for cursor positioning and
// scroll-into-view; without a stub they throw as unhandled exceptions
// during otherwise-passing tests. This is the standard shim used across
// the ProseMirror ecosystem's own jsdom-based test suites.
document.elementFromPoint = () => null;
Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: function* () {} }) as unknown as DOMRectList;
Range.prototype.getBoundingClientRect = () =>
  ({ x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, toJSON: () => ({}) }) as DOMRect;
