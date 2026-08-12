/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0c1a1f",
          900: "#132a33",
          800: "#1c3d4a",
          700: "#2a5363",
          600: "#3a6a7a",
          500: "#4f8494",
          400: "#7aa8b5",
          300: "#a8c8d1",
          200: "#d0e3e8",
          100: "#e8f2f5",
          50: "#f4f9fa",
        },
        sea: {
          700: "#0d6e6e",
          600: "#0f8a8a",
          500: "#14a3a3",
          400: "#2ec4c4",
          300: "#6dd5d5",
        },
        sand: {
          400: "#d4a574",
          300: "#e0bc96",
          200: "#edd4b8",
          100: "#f7eadc",
        },
        coral: {
          600: "#c45c4a",
          500: "#d9705c",
          400: "#e89282",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      fontSize: {
        // Editorial display scale for the public site — large, generous
        // line-height, tight tracking. App dashboard keeps using the
        // default Tailwind scale (text-2xl, text-3xl, etc.) untouched.
        "display-2xl": ["4.5rem", { lineHeight: "1.04", letterSpacing: "-0.02em" }],
        "display-xl": ["3.5rem", { lineHeight: "1.06", letterSpacing: "-0.015em" }],
        "display-lg": ["2.5rem", { lineHeight: "1.1", letterSpacing: "-0.01em" }],
        "display-md": ["1.75rem", { lineHeight: "1.2", letterSpacing: "-0.005em" }],
      },
      backgroundImage: {
        grain:
          "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E\")",
        "hero-wash":
          "radial-gradient(ellipse 80% 60% at 10% 0%, rgba(20,163,163,0.12), transparent 50%), radial-gradient(ellipse 60% 50% at 90% 10%, rgba(212,165,116,0.14), transparent 45%), linear-gradient(180deg, #f4f9fa 0%, #e8f2f5 100%)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s ease-out forwards",
        "fade-in": "fade-in 0.4s ease-out forwards",
        "pulse-soft": "pulse-soft 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
