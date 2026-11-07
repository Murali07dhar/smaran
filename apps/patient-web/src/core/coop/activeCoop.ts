import type { CoopTransport } from "@smaran/games";

// Hand-off between CoopJoinScreen and GameLauncher (module-level; no DOM).
let active: CoopTransport | null = null;
export const setActiveCoop = (t: CoopTransport | null) => { active?.leave(); active = t; };
export const getActiveCoop = () => active;
