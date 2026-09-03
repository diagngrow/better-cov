export default {
  test: {
    coverage: {
      enabled: true,
      include: ["src/lib/tool.ts"],
      provider: "v8",
      reporter: ["cobertura"],
    },
  },
};
