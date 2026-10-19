// Include installed dependency licences alongside the locally served production bundle.
import { readFileSync, existsSync, writeFileSync, readdirSync } from "node:fs";
const lock = JSON.parse(
  readFileSync(new URL("../package-lock.json", import.meta.url)),
);
let text =
  "Zigbee dashboard frontend — third-party notices\n\nVersions are pinned in frontend/package-lock.json. Original project code is MIT.\n";
for (const [path, entry] of Object.entries(lock.packages).sort(([a], [b]) =>
  a.localeCompare(b),
)) {
  if (!path) continue;
  const root = new URL("../" + path + "/", import.meta.url);
  if (!existsSync(root)) continue;
  const pkg = JSON.parse(readFileSync(new URL("package.json", root)));
  text += `\n${"=".repeat(72)}\n${pkg.name} ${pkg.version} — ${pkg.license || entry.license || "See package licence"}\n`;
  const license = readdirSync(root).find((n) =>
    /^licen[sc]e(?:[.-].*)?$/i.test(n),
  );
  if (license)
    text += "\n" + readFileSync(new URL(license, root), "utf8") + "\n";
}
writeFileSync(
  new URL(
    "../../sbc/static/dashboard/assets/third-party-licenses.txt",
    import.meta.url,
  ),
  text,
);
