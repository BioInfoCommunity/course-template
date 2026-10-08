const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");

const CONTENT_DIR = ".";
const OUTPUT_FILE = "./_data/navigation.yml";

// remove leading numbers like 010-
function stripNumber(name) {
  return name.replace(/^\d+-/, "");
}

// convert slug to readable title
function toTitle(str) {
  return stripNumber(str)
    .replace(/-/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());
}

// read title from frontmatter, fall back to generated title
function getFrontmatterTitle(filePath, fallback) {
  try {
    const content = fs.readFileSync(filePath, "utf8");
    const match = content.match(/^---\n([\s\S]*?)\n---/);
    if (match) {
      const fm = yaml.load(match[1]);
      if (fm && fm.title) return fm.title;
    }
  } catch (_) {}
  return fallback;
}

// inject permalink into markdown file
function addPermalink(filePath, permalink) {
  let content = fs.readFileSync(filePath, "utf8");

  // skip if already exists
  if (content.includes("permalink:")) return;

  if (content.startsWith("---")) {
    content = content.replace(
      /^---\n/,
      `---\npermalink: ${permalink}\n`
    );
  } else {
    // no front matter → add it
    content = `---\npermalink: ${permalink}\nlayout: default\n---\n\n${content}`;
  }

  fs.writeFileSync(filePath, content);
}

function getPages(dir, parentUrl = "") {
  const entries = fs.readdirSync(dir, { withFileTypes: true })
    .filter(e => e.isDirectory() || e.name.endsWith(".md"))
    .sort((a, b) => a.name.localeCompare(b.name));

  // ROOT → language folders
  if (parentUrl === "" && dir === CONTENT_DIR) {
    const navigation = {};

    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      if (["_site", "_layouts", "_data", "scripts", ".git"].includes(entry.name)) continue;

      navigation[entry.name] = getPages(
        path.join(dir, entry.name),
        `/${entry.name}`
      );
    }

    return navigation;
  }

  const pages = [];

  for (const entry of entries) {
    const entryPath = path.join(dir, entry.name);

    // ----------------------------
    // FOLDER
    // ----------------------------
    if (entry.isDirectory()) {
      if (["_site", "_layouts", "_data", "scripts", ".git"].includes(entry.name)) continue;

      const rawName = entry.name;
      const cleanName = stripNumber(rawName);

      const folderUrl = `${parentUrl}/${cleanName}`;
      const indexPath = path.join(entryPath, "index.md");

      if (fs.existsSync(indexPath)) {
        // ✅ inject permalink into index.md
        addPermalink(indexPath, `${folderUrl}/`);

        pages.push({
          title: getFrontmatterTitle(indexPath, toTitle(rawName)),
          url: `${folderUrl}/`,
          children: getPages(entryPath, folderUrl),
        });
      } else {
        pages.push(...getPages(entryPath, folderUrl));
      }
    }

    // ----------------------------
    // FILE
    // ----------------------------
    else if (entry.name.endsWith(".md")) {
      if (["index.md", "README.md"].includes(entry.name)) continue;

      const rawName = entry.name.replace(".md", "");
      const cleanName = stripNumber(rawName);

      const fileUrl = `${parentUrl}/${cleanName}/`;

      // ✅ inject permalink into file
      addPermalink(entryPath, fileUrl);

      pages.push({
        title: getFrontmatterTitle(entryPath, toTitle(rawName)),
        url: fileUrl,
      });
    }
  }

  return pages;
}

// ensure _data exists
if (!fs.existsSync("./_data")) fs.mkdirSync("./_data");

// generate navigation
const navigation = getPages(CONTENT_DIR);

console.log("Generated navigation:");
console.log(JSON.stringify(navigation, null, 2));

// write YAML
fs.writeFileSync(OUTPUT_FILE, yaml.dump({ navigation }));

console.log("✅ Navigation generated at:", OUTPUT_FILE);
