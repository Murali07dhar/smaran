import type { FileAdapter } from "../types";
import { db } from "./db";

// Blobs live in IndexedDB (via the `files` table) rather than Cache Storage
// or OPFS so AES-256-at-rest can be applied uniformly by the sync layer
// before bytes ever touch disk (encryption of the blob itself happens where
// it's produced — camera capture / audio recording — this adapter is just
// the local read/write surface). Returns an object URL for immediate display.
export const webFileAdapter: FileAdapter = {
  async save(path, data) {
    await db.files.put({ id: path, blob: data });
    return URL.createObjectURL(data);
  },
  async read(path) {
    const row = await db.files.get(path);
    return row?.blob;
  },
  async url(path) {
    const row = await db.files.get(path);
    return row ? URL.createObjectURL(row.blob) : undefined;
  },
  async remove(path) {
    await db.files.delete(path);
  }
};
