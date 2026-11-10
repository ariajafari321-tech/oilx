// Copy the single-file build to where the bot serves and publishes it.
import { copyFileSync, statSync } from "node:fs";
const out = new URL("../../oilx/dashboard.html", import.meta.url);
copyFileSync(new URL("../dist/index.html", import.meta.url), out);
console.log(`wrote oilx/dashboard.html (${Math.round(statSync(out).size / 1024)} KB)`);
