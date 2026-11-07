export interface DesignTokens {
  color: {
    primary: string;
    accent: string;
    bg: string;
    surface: string;
    text: string;
    muted: string;
    success: string;
    attention: string;
  };
  radius: { base: number };
  font: { base: number; family: string[] };
  touchTarget: { min: number };
  tagline: string;
  productName: string;
}

declare const tokens: DesignTokens;
export default tokens;
