/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          50: "#f0f0f0",
          100: "#d9d9d9",
          200: "#bfbfbf",
          300: "#a6a6a6",
          400: "#8c8c8c",
          500: "#737373",
          600: "#595959",
          700: "#404040",
          800: "#262626",
          900: "#1a1a1a",
          950: "#0d0d0d",
        },
        okx: {
          bg: "#0d0d0d",
          card: "#1a1a1a",
          border: "#2a2a2a",
          green: "#00c076",
          red: "#f6465d",
          yellow: "#f0b90b",
          blue: "#1e80ff",
          text: "#eaecef",
          textDim: "#848e9c",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

/* rebuild */
