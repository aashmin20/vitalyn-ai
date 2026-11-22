import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // The whole app uses the landing palette: Tailwind's colour names are remapped to warm,
        // muted tones so existing classes (slate-*, emerald-*, red-*, amber-*, blue-*) follow it.
        white: "#fbf9f4",
        slate: {
          50: "#f3efe6", 100: "#ebe6da", 200: "#d8d1c3", 300: "#bfb7a6", 400: "#9a9385",
          500: "#6b675e", 600: "#55524a", 700: "#3d3b35", 800: "#2a2925", 900: "#1b1a17", 950: "#121110",
        },
        emerald: {
          50: "#eef3f0", 100: "#dce7e1", 200: "#b9cfc4", 300: "#8fb1a2", 400: "#5f8c7a",
          500: "#3f7262", 600: "#2e5b4f", 700: "#254b41", 800: "#1e3d35", 900: "#17302a", 950: "#10221d",
        },
        red: {
          50: "#f8ecea", 100: "#f1d6d2", 200: "#e4afa8", 300: "#d4857b", 400: "#c45e52",
          500: "#b4372b", 600: "#9c2e24", 700: "#80261e", 800: "#642019", 900: "#4c1913", 950: "#320f0b",
        },
        amber: {
          50: "#f7f0e3", 100: "#efe1c6", 200: "#e2c894", 300: "#d3ad66", 400: "#c49a4c",
          500: "#b8893a", 600: "#9a712e", 700: "#7b5a25", 800: "#5e451d", 900: "#463316", 950: "#2e210e",
        },
        blue: {
          50: "#eef1f3", 100: "#dde3e8", 200: "#bcc7d0", 300: "#95a6b4", 400: "#6e8596",
          500: "#546b7c", 600: "#445767", 700: "#364553", 800: "#2a3641", 900: "#1f2830", 950: "#141a20",
        },
        background: "var(--background)",
        foreground: "var(--foreground)",
        bone: "var(--bone)",
        paper: "var(--paper)",
        ink: { DEFAULT: "var(--ink)", muted: "var(--ink-muted)" },
        line: "var(--line)",
        vital: "var(--vital)",
        alert: "var(--alert)",
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
