/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#10231f",
        moss: "#1f6d59",
        mint: "#dff5eb",
        sand: "#fbfaf6",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Manrope", "Inter", "sans-serif"],
      },
      boxShadow: {
        soft: "0 16px 45px rgba(27, 57, 47, 0.08)",
      },
    },
  },
  plugins: [],
};

