import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#F4F4F2",
          card: "#FFFFFF",
          subtle: "#FAFAF8",
        },
        ink: {
          DEFAULT: "#0A0A0A",
          muted: "#6B7280",
          faint: "#9CA3AF",
        },
        line: {
          DEFAULT: "#E7E7E2",
          subtle: "#EFEFEA",
        },
        accent: {
          green: "#86EFAC",
          greenInk: "#166534",
          red: "#FCA5A5",
          redInk: "#991B1B",
          amber: "#FCD34D",
          amberInk: "#92400E",
          blue: "#BFDBFE",
          blueInk: "#1E3A8A",
        },
      },
      borderRadius: {
        xl: "14px",
        "2xl": "20px",
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.04)",
        elev: "0 4px 16px -4px rgb(0 0 0 / 0.08)",
      },
    },
  },
  plugins: [],
};
export default config;
