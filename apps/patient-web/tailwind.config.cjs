/** @type {import('tailwindcss').Config} */
module.exports = {
  presets: [require("@smaran/design-tokens/tailwind-preset.js")],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {}
  },
  plugins: []
};
