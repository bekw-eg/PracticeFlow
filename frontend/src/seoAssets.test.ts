import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("public SEO assets", () => {
  it("declares the required metadata on the authenticated SPA shell", async () => {
    const html = await readFile(resolve(process.cwd(), "index.html"), "utf8");

    expect(html).toContain('name="description"');
    expect(html).toContain('name="robots" content="noindex, nofollow"');
    expect(html).toContain('property="og:title"');
    expect(html).toContain('property="og:description"');
    expect(html).toContain('property="og:type" content="website"');
    expect(html).toContain('rel="canonical" href="/login"');
  });

  it("ships real crawl-control files without private application routes", async () => {
    const [robots, sitemap] = await Promise.all([
      readFile(resolve(process.cwd(), "public", "robots.txt"), "utf8"),
      readFile(resolve(process.cwd(), "public", "sitemap.xml"), "utf8"),
    ]);

    expect(robots).toContain("User-agent: *");
    expect(robots).toContain("Disallow: /");
    expect(sitemap).toContain('<?xml version="1.0" encoding="UTF-8"?>');
    expect(sitemap).not.toMatch(/\/(admin|groups|reports|templates|profile)/);
  });
});
