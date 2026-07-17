#!/usr/bin/env npx tsx
/**
 * Apply an organization plan: create folders, rename docs, move docs.
 * Plan JSON: { folders: [name], renames: [{id, newName}], moves: [{folder, ids: []}] }
 * All doc references are by immutable id; hashes are resolved fresh before each phase.
 */
import { initApi } from "./common.js";
import { readFile } from "fs/promises";

async function freshMaps(api: any) {
  const items = await api.listItems(true);
  const byId = new Map(items.map((i: any) => [i.id, i]));
  const folderIdByName = new Map(
    items.filter((i: any) => i.type === "CollectionType").map((i: any) => [i.visibleName, i.id])
  );
  return { byId, folderIdByName };
}

async function main() {
  const plan = JSON.parse(await readFile(process.argv[2], "utf-8"));
  const api = await initApi();

  // Phase 1: folders
  let { folderIdByName } = await freshMaps(api);
  for (const name of plan.folders ?? []) {
    if (folderIdByName.has(name)) {
      console.log(`folder exists: ${name}`);
      continue;
    }
    const e = await api.putFolder(name);
    console.log(`folder created: ${name} (${e.id})`);
  }

  // Phase 2: renames
  let maps = await freshMaps(api);
  for (const r of plan.renames ?? []) {
    const item: any = maps.byId.get(r.id);
    if (!item) {
      console.log(`RENAME SKIP (not found): ${r.id}`);
      continue;
    }
    if (item.visibleName === r.newName) {
      console.log(`rename already applied: ${r.newName}`);
      continue;
    }
    await api.rename(item.hash, r.newName);
    console.log(`renamed: "${item.visibleName}" -> "${r.newName}"`);
    maps = await freshMaps(api); // hashes shift after each write
  }

  // Phase 3: moves (bulk per target folder)
  maps = await freshMaps(api);
  for (const mv of plan.moves ?? []) {
    const folderId = maps.folderIdByName.get(mv.folder);
    if (!folderId) {
      console.log(`MOVE SKIP (no folder): ${mv.folder}`);
      continue;
    }
    const hashes = mv.ids
      .map((id: string) => (maps.byId.get(id) as any))
      .filter((i: any) => i && i.parent !== folderId)
      .map((i: any) => i.hash);
    if (!hashes.length) {
      console.log(`nothing to move -> ${mv.folder}`);
      continue;
    }
    await api.bulkMove(hashes, folderId as string);
    console.log(`moved ${hashes.length} docs -> ${mv.folder}`);
    maps = await freshMaps(api);
  }

  // Phase 4: folder moves (nest folders)
  maps = await freshMaps(api);
  for (const fm of plan.folderMoves ?? []) {
    const item: any = maps.byId.get(maps.folderIdByName.get(fm.name) as string);
    const parentId = maps.folderIdByName.get(fm.parent);
    if (!item || !parentId) {
      console.log(`FOLDER MOVE SKIP: ${fm.name} -> ${fm.parent}`);
      continue;
    }
    if (item.parent === parentId) {
      console.log(`folder already nested: ${fm.name}`);
      continue;
    }
    await api.move(item.hash, parentId as string);
    console.log(`folder moved: ${fm.name} -> ${fm.parent}`);
    maps = await freshMaps(api);
  }

  // Phase 5: delete now-empty folders
  maps = await freshMaps(api);
  for (const name of plan.deleteEmptyFolders ?? []) {
    const fid = maps.folderIdByName.get(name);
    const folder: any = fid && maps.byId.get(fid);
    if (!folder) {
      console.log(`DELETE SKIP (no folder): ${name}`);
      continue;
    }
    const children = [...maps.byId.values()].filter((i: any) => i.parent === fid);
    if (children.length > 0) {
      console.log(`DELETE SKIP (not empty, ${children.length} items): ${name}`);
      continue;
    }
    await api.delete(folder.hash);
    console.log(`empty folder deleted: ${name}`);
    maps = await freshMaps(api);
  }

  console.log("done");
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
