import { defineConfig } from "vite";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/unit/**/*.spec.ts"]
  }
});
