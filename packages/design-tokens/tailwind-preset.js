// Tailwind preset generated from tokens.json so web and (later) React Native
// read the exact same source of truth. Do not hardcode colors elsewhere.
const tokens = require("./tokens.json");

/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: tokens.color.primary,
        accent: tokens.color.accent,
        bg: tokens.color.bg,
        surface: tokens.color.surface,
        text: tokens.color.text,
        muted: tokens.color.muted,
        success: tokens.color.success,
        attention: tokens.color.attention
      },
      borderRadius: {
        token: `${tokens.radius.base}px`
      },
      fontSize: {
        base: `${tokens.font.base}px`
      },
      fontFamily: {
        sans: tokens.font.family
      },
      spacing: {
        touch: `${tokens.touchTarget.min}px`
      }
    }
  }
};
