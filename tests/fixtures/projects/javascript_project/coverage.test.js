const { run } = require("./src/module");

test("runs the selected branch", () => {
  expect(run(true)).toBe(1);
});
