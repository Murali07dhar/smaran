import assam from '../packs/assam.json';
import photos from '../packs/demo_photos.json';
import routines from '../packs/routines.json';
import type { ContentPack, PackItem } from './validate';
export * from './validate';
export const packs = { assam, demo_photos: photos, routines } as unknown as Record<string, ContentPack>;
/** All bundled items (culture objects, stand-in photos, routine steps). Caregiver photos are added by the host at runtime. */
export const allItems: PackItem[] = Object.values(packs).flatMap((p) => p.items);
export const categories = ['instruments', 'textiles', 'food', 'festivals'] as const;
export const routineIds = ['morning', 'make_tea'] as const;
