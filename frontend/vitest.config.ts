import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    root: path.resolve(__dirname, ".."),
    environment: "jsdom",
    globals: true,
    setupFiles: ["tests/frontend/setup.ts"],
    include: ["tests/frontend/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["frontend/src/**/*.{ts,tsx}"],
      exclude: ["frontend/src/vite-env.d.ts", "frontend/src/main.tsx"],
    },
  },
});
