#!/usr/bin/env npx tsx
/** Dump full document inventory as JSON: id, hash, name, parent, type, modified. */
import { initApi } from "./common.js";

async function main() {
  const api = await initApi();
  const items = await api.listItems(true);
  const out = items.map((i: any) => ({
    id: i.id,
    hash: i.hash,
    name: i.visibleName,
    type: i.type,
    parent: i.parent ?? "",
    lastModified: i.lastModified,
    fileType: i.fileType,
    pinned: i.pinned,
  }));
  console.log(JSON.stringify(out, null, 1));
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
