import type { FileAdapter, KeyValueAdapter } from '../../../core/types';

// Own tiny IndexedDB DB ("smaran-voice") so this package does not depend on the patient-web Dexie schema.
// The integrator may swap these for the shared StorageAdapter.
const DB_NAME = 'smaran-voice';

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      db.createObjectStore('files');
      db.createObjectStore('kv');
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return open().then((db) => new Promise<T>((resolve, reject) => {
    const r = fn(db.transaction(store, mode).objectStore(store));
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  }));
}

export class IdbFileAdapter implements FileAdapter {
  async read(key: string) { return ((await tx('files', 'readonly', (s) => s.get(key))) as ArrayBuffer | undefined) ?? null; }
  async write(key: string, data: ArrayBuffer) { await tx('files', 'readwrite', (s) => s.put(data, key)); }
  async remove(key: string) { await tx('files', 'readwrite', (s) => s.delete(key)); }
  async list(prefix: string) {
    const keys = (await tx('files', 'readonly', (s) => s.getAllKeys())) as string[];
    return keys.filter((k) => k.startsWith(prefix));
  }
}

export class IdbKeyValueAdapter implements KeyValueAdapter {
  async get<T>(key: string) { return (await tx('kv', 'readonly', (s) => s.get(key))) as T | undefined; }
  async set<T>(key: string, value: T) { await tx('kv', 'readwrite', (s) => s.put(value, key)); }
  async delete(key: string) { await tx('kv', 'readwrite', (s) => s.delete(key)); }
}
