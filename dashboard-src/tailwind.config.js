/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#09090b", 900: "#0c0c0f", 850: "#101014", 800: "#15151a", 700: "#1d1d23" },
        line: { DEFAULT: "#27272a", soft: "#1c1c20" },
        crude: { DEFAULT: "#c9a25e", bright: "#e0bd7c", dim: "#8a6f3f", wash: "rgba(201,162,94,0.08)" },
        bull: { DEFAULT: "#4fae87", wash: "rgba(79,174,135,0.12)" },
        bear: { DEFAULT: "#d2625a", wash: "rgba(210,98,90,0.12)" },
        warn: { DEFAULT: "#e08a3c", wash: "rgba(224,138,60,0.12)" },
      },
      fontFamily: {
        sans: ['"Geist Variable"', "Inter", "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
        mono: ['"Geist Mono Variable"', "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
      keyframes: {
        ping2: { "0%": { transform: "scale(1)", opacity: ".55" }, "80%,100%": { transform: "scale(2.6)", opacity: "0" } },
        spinborder: { to: { transform: "rotate(360deg)" } },
        rise: { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        caret: { "0%,49%": { opacity: "1" }, "50%,100%": { opacity: "0" } },
        shimmer: { from: { backgroundPosition: "200% 0" }, to: { backgroundPosition: "-200% 0" } },
      },
      animation: {
        ping2: "ping2 2.2s cubic-bezier(0,0,.2,1) infinite",
        spinborder: "spinborder 5s linear infinite",
        rise: "rise .5s cubic-bezier(.22,1,.36,1) both",
        caret: "caret 1s steps(1) infinite",
        shimmer: "shimmer 2.4s linear infinite",
      },
      transitionTimingFunction: { spring: "cubic-bezier(.22,1,.36,1)" },
    },
  },
  plugins: [],
};
