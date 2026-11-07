import type { MediaAsset } from "@smaran/contracts";
import type { FileAdapter, StorageAdapter } from "../../adapters/types";
import type { ApiClient } from "../api/client";
import { getMedia, getMediaUrl } from "../api/endpoints";

// PORTABILITY: fetch + adapters only. Caregiver photos/audio are downloaded once (signed URL, relative to the
// API base) and kept in the FileAdapter so games can use them with the network fully off.
const MEDIA_TABLE = "media";
const filePath = (id: string) => `media/${id}`;

/** Prefix a relative signed URL (`/api/v1/media/..`) with the API origin when the base is absolute. */
export function absoluteUrl(apiBase: string, relative: string): string {
  if (/^https?:/.test(relative)) return relative;
  const m = /^(https?:\/\/[^/]+)/.exec(apiBase);
  return (m ? m[1] : "") + relative;
}

export async function refreshMediaList(client: ApiClient, storage: StorageAdapter, patientId: string): Promise<MediaAsset[]> {
  const list = await getMedia(client, patientId);
  await storage.bulkPut(MEDIA_TABLE, list);
  return list;
}

export async function ensureLocal(
  client: ApiClient, files: FileAdapter, apiBase: string, media: MediaAsset
): Promise<string | undefined> {
  const existing = await files.url(filePath(media.id));
  if (existing) return existing;
  try {
    const { url } = await getMediaUrl(client, media.id);
    const res = await fetch(absoluteUrl(apiBase, url));
    if (!res.ok) return undefined;
    await files.save(filePath(media.id), await res.blob());
    return files.url(filePath(media.id));
  } catch {
    return undefined; // offline and not cached yet
  }
}

/** Local media for a patient, with a displayable URL for every asset already cached. */
export async function localMedia(
  storage: StorageAdapter, files: FileAdapter, patientId: string
): Promise<Array<{ media: MediaAsset; url?: string }>> {
  const all = await storage.getAll<MediaAsset>(MEDIA_TABLE);
  const mine = all.filter((m) => m.patient_id === patientId);
  return Promise.all(mine.map(async (media) => ({ media, url: await files.url(filePath(media.id)) })));
}
