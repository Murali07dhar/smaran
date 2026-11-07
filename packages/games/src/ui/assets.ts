let base = '';
/** Host sets where content assets are served from (web: '/', RN: file/asset resolver replaces this module). */
export const setAssetBase = (b: string) => { base = !b || b.endsWith('/') ? b : `${b}/`; };
export const assetUrl = (p?: string) => (!p ? '' : /^(https?:|data:|blob:|file:|\/)/.test(p) ? p : base + p);
