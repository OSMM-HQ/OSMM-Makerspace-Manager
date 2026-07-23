import { describe, expect, it } from "vitest";
import { TAB_LABELS } from "./staffAccess";
import { staffPathState, tabFromStaffPath } from "./staffTabs";

describe("staff printing route alias", () => {
  it("maps the legacy deep link to Machines", () => {
    expect(tabFromStaffPath("/admin/printing", false)).toBe("machines");
    expect(staffPathState("/m/forge/admin/printing", false)).toEqual({ makerspaceSlug: "forge", tab: "machines" });
  });

  it("uses a generic label for the multi-integration platform tab", () => {
    expect(TAB_LABELS.platform).toBe("Platform settings");
  });
});
