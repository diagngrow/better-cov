import { describe, expect, it } from "vitest";

import { run } from "./src/lib/tool";

describe("run", () => {
  it("runs the selected branch", () => {
    expect(run(true)).toBe(1);
  });
});
