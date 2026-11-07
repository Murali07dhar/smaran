import type { StorageAdapter } from "../types";
import { db } from "./db";

function table(name: string) {
  const t = (db as any)[name];
  if (!t) throw new Error(`Unknown local table: ${name}`);
  return t;
}

export const webStorageAdapter: StorageAdapter = {
  async put(tableName, record) {
    await table(tableName).put(record);
  },
  async bulkPut(tableName, records) {
    await table(tableName).bulkPut(records);
  },
  async get(tableName, id) {
    return table(tableName).get(id);
  },
  async getAll(tableName) {
    return table(tableName).toArray();
  },
  async query(tableName, predicate) {
    const all = await table(tableName).toArray();
    return all.filter(predicate);
  },
  async delete(tableName, id) {
    await table(tableName).delete(id);
  },
  async clear(tableName) {
    await table(tableName).clear();
  }
};
