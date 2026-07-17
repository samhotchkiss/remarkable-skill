#!/usr/bin/env npx tsx
/** Download a set of documents given a JSON file of {id, hash, name} and an output dir. */
import { initApi, safeName } from "./common.js";
import { writeFile, mkdir, readFile } from "fs/promises";
import { join } from "path";

async function main() {
  const [listFile, outDir] = process.argv.slice(2);
  const targets = JSON.parse(await readFile(listFile, "utf-8"));
  const api = await initApi();
  await mkdir(outDir, { recursive: true });

  for (const t of targets) {
    try {
      const zipData = await api.getDocument(t.id, t.hash);
      const p = join(outDir, `${safeName(t.name)}__${t.id.slice(0, 8)}.zip`);
      await writeFile(p, zipData);
      console.log(`ok ${t.name}`);
      await new Promise((r) => setTimeout(r, 150));
    } catch (e: any) {
      console.log(`FAIL ${t.name}: ${e.message}`);
    }
  }
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
