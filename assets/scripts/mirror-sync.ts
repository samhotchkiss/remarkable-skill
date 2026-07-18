#!/usr/bin/env npx tsx
/**
 * mirror-sync.ts — one sync pass for the local reMarkable mirror.
 *
 * Mirrors the cloud library to $REMARKABLE_MIRROR (default ~/reMarkable):
 *   <Folder path>/<Doc Name>/
 *     raw/           extracted .rm archive (programmatic access)
 *     render.pdf     faithful render (colors, highlighters, pressure)
 *     pages/         page-NN.png — read these to see the doc
 *     delta/         delta-NN.png — NEW strokes since previous sync in color,
 *                    older ink faded gray (only for changed pages)
 *     meta.json      id, hash, timestamps, page count, changed pages
 *   INDEX.md         whole-library tree + recent-change list (read this first)
 *   CHANGELOG.jsonl  append-only sync events
 *
 * Change detection is by document hash (hashes mutate on every edit).
 * Designed to run under launchd every few minutes; single-instance via lockfile.
 */
import { initApi, safeName } from "./common.js";
import { execFileSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

const MIRROR = process.env.REMARKABLE_MIRROR || path.join(os.homedir(), "reMarkable");
const STATE_DIR = path.join(MIRROR, ".mirror");
const STATE = path.join(STATE_DIR, "state.json");
const LOCK = path.join(STATE_DIR, "lock");
const PAGE_CAP = 80;

function log(msg: string) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

function loadState(): any {
  try {
    return JSON.parse(fs.readFileSync(STATE, "utf-8"));
  } catch {
    return { docs: {} };
  }
}

async function main() {
  fs.mkdirSync(STATE_DIR, { recursive: true });

  // single-instance lock (stale after 30 min)
  if (fs.existsSync(LOCK)) {
    const age = Date.now() - fs.statSync(LOCK).mtimeMs;
    if (age < 30 * 60 * 1000) {
      log("another sync is running; exiting");
      return;
    }
  }
  fs.writeFileSync(LOCK, String(process.pid));

  try {
    const api = await initApi();
    const items: any[] = await api.listItems(true);
    const state = loadState();

    const folders = new Map(items.filter((i) => i.type === "CollectionType").map((i) => [i.id, i]));
    const docs = items.filter((i) => i.type === "DocumentType" && i.parent !== "trash");

    const relPath = (doc: any): string => {
      const parts = [safeName(doc.visibleName)];
      let cur = doc.parent;
      while (cur && cur !== "" && folders.has(cur)) {
        const f: any = folders.get(cur);
        if (f.parent === "trash") return ""; // inside trashed folder
        parts.unshift(safeName(f.visibleName));
        cur = f.parent;
      }
      return cur === "trash" ? "" : parts.join("/");
    };

    const events: any[] = [];
    const seen = new Set<string>();

    for (const doc of docs) {
      const rel = relPath(doc);
      if (!rel) continue;
      seen.add(doc.id);
      const prev = state.docs[doc.id];
      const docDir = path.join(MIRROR, rel);

      // moved/renamed: relocate existing mirror dir so stroke history survives
      if (prev && prev.rel !== rel && fs.existsSync(path.join(MIRROR, prev.rel))) {
        fs.mkdirSync(path.dirname(docDir), { recursive: true });
        fs.renameSync(path.join(MIRROR, prev.rel), docDir);
        events.push({ t: Date.now(), event: "moved", name: doc.visibleName, from: prev.rel, to: rel });
      }

      if (prev && prev.hash === doc.hash && fs.existsSync(docDir)) {
        state.docs[doc.id] = { hash: doc.hash, rel, name: doc.visibleName };
        continue; // unchanged
      }

      log(`syncing: ${rel}`);
      try {
        const zip = await api.getDocument(doc.id, doc.hash);
        const rawDir = path.join(docDir, "raw");
        fs.rmSync(rawDir, { recursive: true, force: true });
        fs.mkdirSync(rawDir, { recursive: true });
        const zipPath = path.join(docDir, ".doc.zip");
        fs.writeFileSync(zipPath, zip);
        execFileSync("unzip", ["-o", "-q", zipPath, "-d", rawDir]);
        fs.unlinkSync(zipPath);

        // render (pdf + pages + deltas) — python does the heavy lifting
        const skillDir = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
        const py = path.join(skillDir, ".venv/bin/python");
        const renderer = path.join(skillDir, "assets/scripts/mirror-render.py");
        const outJson = execFileSync(py, [renderer, docDir, String(PAGE_CAP)], { encoding: "utf-8" });
        const summary = JSON.parse(outJson.trim().split("\n").pop() || "{}");

        fs.writeFileSync(
          path.join(docDir, "meta.json"),
          JSON.stringify(
            { id: doc.id, hash: doc.hash, name: doc.visibleName, rel, syncedAt: new Date().toISOString(), ...summary },
            null,
            2
          )
        );
        state.docs[doc.id] = { hash: doc.hash, rel, name: doc.visibleName };
        events.push({
          t: Date.now(),
          event: prev ? "updated" : "added",
          name: doc.visibleName,
          rel,
          changedPages: summary.changedPages ?? [],
        });
        await new Promise((r) => setTimeout(r, 150));
      } catch (e: any) {
        log(`FAIL ${rel}: ${e.message}`);
      }
    }

    // trashed/deleted docs -> .mirror/trash
    for (const [id, info] of Object.entries<any>(state.docs)) {
      if (!seen.has(id)) {
        const src = path.join(MIRROR, info.rel);
        if (fs.existsSync(src)) {
          const dst = path.join(STATE_DIR, "trash", `${safeName(info.name)}-${id.slice(0, 8)}`);
          fs.mkdirSync(path.dirname(dst), { recursive: true });
          fs.rmSync(dst, { recursive: true, force: true });
          fs.renameSync(src, dst);
        }
        events.push({ t: Date.now(), event: "trashed", name: info.name, rel: info.rel });
        delete state.docs[id];
      }
    }

    fs.writeFileSync(STATE, JSON.stringify(state, null, 2));

    if (events.length) {
      fs.appendFileSync(path.join(MIRROR, "CHANGELOG.jsonl"), events.map((e) => JSON.stringify(e)).join("\n") + "\n");
    }

    // INDEX.md — the one file an agent reads first
    const lines: string[] = [
      "# reMarkable mirror",
      "",
      `Synced: ${new Date().toISOString()} · ${docs.length} documents`,
      "",
      "Per document: `pages/page-NN.png` (current state), `delta/delta-NN.png`",
      "(NEW ink in color, old ink faded — check these to see fresh annotations),",
      "`render.pdf`, `raw/` (.rm archive), `meta.json`.",
      "Recent events: see CHANGELOG.jsonl (append-only).",
      "",
      "## Recently updated",
      "",
    ];
    let chlog: any[] = [];
    try {
      chlog = fs
        .readFileSync(path.join(MIRROR, "CHANGELOG.jsonl"), "utf-8")
        .trim()
        .split("\n")
        .slice(-15)
        .map((l) => JSON.parse(l));
    } catch {}
    for (const e of chlog.reverse()) {
      lines.push(`- ${new Date(e.t).toISOString()} — ${e.event}: ${e.rel ?? e.name}${e.changedPages?.length ? ` (pages ${e.changedPages.map((p: number) => p + 1).join(", ")})` : ""}`);
    }
    lines.push("", "## Library", "");
    const byRel = Object.values<any>(state.docs).sort((a, b) => a.rel.localeCompare(b.rel));
    for (const d of byRel) lines.push(`- ${d.rel}`);
    fs.writeFileSync(path.join(MIRROR, "INDEX.md"), lines.join("\n") + "\n");

    log(`done — ${events.length} change(s)`);
  } finally {
    fs.rmSync(LOCK, { force: true });
  }
}

main().catch((e) => {
  console.error(e);
  fs.rmSync(LOCK, { force: true });
  process.exit(1);
});
