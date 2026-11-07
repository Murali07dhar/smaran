// @ts-expect-error CJS preset from the shared workspace package
import preset from '@smaran/design-tokens/tailwind-preset.js';
export default { presets: [preset], content: ['./index.html', './src/**/*.{ts,tsx}'] };
