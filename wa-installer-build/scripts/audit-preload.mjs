import { mkdtempSync } from "node:fs";
import { register } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
const dir = mkdtempSync(path.join(tmpdir(), "wa-audit-"));
process.env.WHATSAPP_SQLITE_PATH = path.join(dir, "audit.sqlite");
register(new URL("./audit-loader.mjs", import.meta.url));
