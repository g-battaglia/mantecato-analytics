import { defineConfig } from "tsup";

export default defineConfig([
  // Main library (ESM + CJS)
  {
    entry: ["src/index.ts"],
    format: ["esm", "cjs"],
    dts: true,
    clean: true,
    sourcemap: true,
    minify: false,
    target: "es2020",
  },
  // Drop-in script (single IIFE file for <script> tag)
  {
    entry: ["src/script.ts"],
    format: ["iife"],
    globalName: "mantecato",
    outDir: "dist",
    clean: false,
    sourcemap: false,
    minify: true,
    target: "es2017",
    outExtension: () => ({ js: ".js" }),
  },
]);
