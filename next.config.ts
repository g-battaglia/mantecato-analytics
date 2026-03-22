import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: {
    resolveAlias: {
      // Force fflate to use its browser build during client SSR
      // (the node build uses Worker which Turbopack can't resolve)
      fflate: "fflate/browser",
    },
  },
};

export default nextConfig;
