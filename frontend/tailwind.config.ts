import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#090d16",
        panel: "#111827",
        accent: "#7c8cff",
      },
    },
  },
  plugins: [],
};

export default config;
