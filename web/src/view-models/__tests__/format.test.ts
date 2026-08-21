import { describe, expect, it } from "vitest";

import { formatBytes } from "../format";

describe("formatBytes", () => {
  it("renders whole megabytes without a decimal point", () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe("5 MB");
    expect(formatBytes(20 * 1024 * 1024)).toBe("20 MB");
  });

  it("keeps one decimal for fractional megabytes", () => {
    expect(formatBytes(1.5 * 1024 * 1024)).toBe("1.5 MB");
  });

  // Below a megabyte "0 MB" would read as "uploads are impossible", so the
  // unit drops rather than the precision.
  it("falls back to kilobytes under a megabyte", () => {
    expect(formatBytes(512 * 1024)).toBe("512 KB");
  });
});
