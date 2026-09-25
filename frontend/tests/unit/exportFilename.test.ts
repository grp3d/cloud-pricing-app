import { describe, expect, it } from "vitest";

import { buildExportFilename } from "../../src/lib/exportFilename";

describe("buildExportFilename", () => {
  it("names the file <username>_<local YYYYMMDDTHHMMSS>.json (FR-013)", () => {
    expect(buildExportFilename("jdoe", new Date(2026, 8, 25, 14, 30, 22))).toBe(
      "jdoe_20260925T143022.json",
    );
  });

  it("zero-pads every date and time part", () => {
    expect(buildExportFilename("Admin", new Date(2026, 0, 2, 3, 4, 5))).toBe(
      "Admin_20260102T030405.json",
    );
  });

  it("replaces characters unsafe in desktop filenames with underscores", () => {
    expect(buildExportFilename("a b/c:d\\e*f", new Date(2026, 8, 25, 0, 0, 0))).toBe(
      "a_b_c_d_e_f_20260925T000000.json",
    );
  });

  it("keeps letters, digits, dots, hyphens and underscores", () => {
    expect(buildExportFilename("j.doe-2_x", new Date(2026, 8, 25, 0, 0, 0))).toBe(
      "j.doe-2_x_20260925T000000.json",
    );
  });
});
