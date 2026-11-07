// Pure pack validator (mirrors schema/content-pack.schema.json; no ajv dependency so it runs on-device too).
export interface PackItem { id: string; kind: 'object' | 'photo' | 'step'; category: string; labels: Record<string, string>; image?: string; icon?: string; source: 'cc0' | 'placeholder' | 'caregiver'; tags?: string[]; routine_id?: string; step_order?: number }
export interface ContentPack { pack_id: string; version: string; license: 'CC0-1.0'; locales: string[]; items: PackItem[] }
const CATS = ['instruments', 'textiles', 'food', 'festivals'];
export function validatePack(p: ContentPack): string[] {
  const e: string[] = [];
  if (!p.pack_id) e.push('pack_id missing');
  if (!/^\d+\.\d+\.\d+$/.test(p.version)) e.push('version must be semver');
  if (p.license !== 'CC0-1.0') e.push('license must be CC0-1.0');
  const ids = new Set<string>();
  for (const i of p.items) {
    if (ids.has(i.id)) e.push(`duplicate id ${i.id}`);
    ids.add(i.id);
    if (!i.labels?.en) e.push(`${i.id}: en label required`);
    if (p.locales.includes('as') && !i.labels?.as) e.push(`${i.id}: as label required`);
    if (i.kind === 'step' && (!i.routine_id || !i.step_order)) e.push(`${i.id}: step needs routine_id and step_order`);
    if (i.kind !== 'step' && !i.image && !i.icon) e.push(`${i.id}: needs image or icon`);
    if (i.kind === 'object' && !CATS.includes(i.category)) e.push(`${i.id}: unknown category ${i.category}`);
  }
  return e;
}
