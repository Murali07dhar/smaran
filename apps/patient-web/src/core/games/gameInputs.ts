import { allItems } from "@smaran/content";
import { EMOTION_LABELS, type MediaAsset } from "@smaran/contracts";
import type { ContentItem, Cue, EmotionLabel } from "@smaran/games";

// PORTABILITY: pure functions, no DOM. Builds GameProps.content / GameProps.cues.

/** Bundled CC0/placeholder items (packages/content) as game content. */
export function bundledContent(): ContentItem[] {
  return allItems as unknown as ContentItem[];
}

const LABELS = new Set<string>(EMOTION_LABELS);

/** Tags convention: free strings; any emotion label sets valence_label, `item:<id>` links the cue to a content item,
 *  `label:<text>` names it. Untagged caregiver media defaults to `familiarity` (positive-valence cue). */
export function cueFromMedia(media: MediaAsset, url: string): Cue | undefined {
  if (media.kind !== "photo" && media.kind !== "audio") return undefined;
  const tags = Array.isArray(media.tags) ? (media.tags as unknown[]).map(String) : [];
  const valence = (tags.find((t) => LABELS.has(t)) as EmotionLabel | undefined) ?? "familiarity";
  const item = tags.find((t) => t.startsWith("item:"))?.slice(5);
  const label = tags.find((t) => t.startsWith("label:"))?.slice(6);
  return { cue_id: media.id, cue_type: media.kind, uri: url, label, valence_label: valence, item_id: item };
}

export function cuesFromLocalMedia(rows: Array<{ media: MediaAsset; url?: string }>): Cue[] {
  return rows.flatMap((r) => (r.url ? [cueFromMedia(r.media, r.url)].filter((c): c is Cue => !!c) : []));
}

/** Caregiver photos also become playable content items (source "caregiver"). */
export function caregiverPhotoItems(rows: Array<{ media: MediaAsset; url?: string }>): ContentItem[] {
  return rows
    .filter((r) => r.media.kind === "photo" && r.url)
    .map((r) => {
      const tags = Array.isArray(r.media.tags) ? (r.media.tags as unknown[]).map(String) : [];
      const label = tags.find((t) => t.startsWith("label:"))?.slice(6) ?? "Family photo";
      return {
        id: `cg_${r.media.id}`, kind: "photo" as const, category: "family",
        labels: { en: label, as: label }, image: r.url, source: "caregiver" as const, tags
      };
    });
}
