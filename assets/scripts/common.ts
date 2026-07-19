/**
 * Common utilities for reMarkable API operations
 *
 * Usage: import { getDeviceToken, initApi, findDocument } from "./common.js"
 */

import { remarkable, type RemarkableApi, type Entry } from "rmapi-js";
import { readFileSync, writeFileSync, mkdirSync, chmodSync } from "fs";
import * as path from "path";

function tokenFilePath(): string {
  return process.env.REMARKABLE_TOKEN_FILE || `${process.env.HOME}/.config/remarkable/device_token`;
}

/**
 * Retrieve the device token from the local token file.
 * This is the ONLY auth source — no secret-manager fallbacks (they require
 * interactive authorization, which headless/remote sessions can't provide).
 * @throws Error with registration instructions if the token is missing
 */
export async function getDeviceToken(): Promise<string> {
  try {
    const token = readFileSync(tokenFilePath(), "utf-8").trim();
    if (token) return token;
  } catch {
    // fall through to error below
  }
  throw new Error(
    `Device token not found at ${tokenFilePath()}. Register this device first:\n` +
      "1. Go to https://my.remarkable.com/device/browser/connect\n" +
      "2. Get the 8-character code\n" +
      "3. Run: npx tsx assets/scripts/register.ts <code>"
  );
}

/**
 * Store the device token in the local token file (mode 600).
 * @returns true if successful
 */
export function storeDeviceToken(token: string): boolean {
  try {
    const file = tokenFilePath();
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, token.trim() + "\n");
    chmodSync(file, 0o600);
    return true;
  } catch {
    return false;
  }
}

/**
 * Initialize reMarkable API with the device token from the local token file
 * @returns Initialized API instance
 */
export async function initApi(): Promise<RemarkableApi> {
  const deviceToken = await getDeviceToken();
  return remarkable(deviceToken);
}

/**
 * Fuzzy search for documents by name
 * @param items - List of entries from api.listItems()
 * @param query - Search query
 * @returns Matching documents sorted by relevance
 */
export function findDocuments(items: Entry[], query: string): Entry[] {
  const queryLower = query.toLowerCase();
  return items
    .filter((item) => item.type === "DocumentType")
    .filter((item) => item.visibleName.toLowerCase().includes(queryLower))
    .sort((a, b) => {
      const aName = a.visibleName.toLowerCase();
      const bName = b.visibleName.toLowerCase();

      // Exact match first
      if (aName === queryLower) return -1;
      if (bName === queryLower) return 1;

      // Prefix match second
      if (aName.startsWith(queryLower) && !bName.startsWith(queryLower)) return -1;
      if (bName.startsWith(queryLower) && !aName.startsWith(queryLower)) return 1;

      // Alphabetical for contains matches
      return aName.localeCompare(bName);
    });
}

/**
 * Find folders from item list
 * @param items - List of entries from api.listItems()
 * @returns Map of folder ID to folder entry
 */
export function getFolders(items: Entry[]): Map<string, Entry & { children: Entry[] }> {
  const folders = new Map<string, Entry & { children: Entry[] }>();

  for (const item of items) {
    if (item.type === "CollectionType") {
      folders.set(item.id, { ...item, children: [] });
    }
  }

  // Add documents to their parent folders
  for (const item of items) {
    if (item.type === "DocumentType" && item.parent && folders.has(item.parent)) {
      folders.get(item.parent)!.children.push(item);
    }
  }

  return folders;
}

/**
 * Build folder path string for a document
 * @param item - Document entry
 * @param folders - Folder map from getFolders()
 * @returns Path string like "Folder/Subfolder"
 */
export function getPath(item: Entry, folders: Map<string, Entry & { children: Entry[] }>): string {
  const parts: string[] = [];
  let current = item.parent;

  while (current && current !== "" && current !== "trash") {
    const folder = folders.get(current);
    if (folder) {
      parts.unshift(folder.visibleName);
      current = folder.parent;
    } else {
      break;
    }
  }

  return parts.join("/");
}

/**
 * Sanitize filename for filesystem
 * @param name - Original name
 * @returns Safe filename
 */
export function safeName(name: string): string {
  return name.replace(/[^a-zA-Z0-9-_. ]/g, "_").replace(/\s+/g, "_");
}

/**
 * Get today's date in YYYY-MM-DD format
 */
export function today(): string {
  return new Date().toISOString().split("T")[0];
}
