import type { VercelConfig } from "@vercel/config/v1";

export const config: VercelConfig = {
  framework: "nextjs",
  buildCommand: "npm run build",
  installCommand: "npm install",
  headers: [
    {
      source: "/api/revalidate",
      headers: [{ key: "Cache-Control", value: "no-store" }],
    },
  ],
};
