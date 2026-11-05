#!/usr/bin/env node
/**
 * init_session.js
 * Deterministic session initialization and metadata generation for SAP Data Products.
 * Strictly implements Step 1b of the Data Product lifecycle specification.
 *
 * Usage:
 *     node init_session.js \
 *         --name "NetRevenuePerformance" \
 *         --source-dps '[{"ordId":"sap.s4com:dataProduct:BillingDocument:v1","version":"1.6.0"}]' \
 *         [--solution-id "44026fb1-0e1e-4ac2-acdb-adcdf85cf10f"] \
 *         [--title "Net Revenue Performance"] \
 *         [--short-desc "Short description"] \
 *         [--desc "Full description"] \
 *         [--responsible "customer:vendor:Customer"] \
 *         [--workspace-dir "."] \
 *         [--overwrite]
 */

import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

/**
 * Prints diagnostic step message to stderr for real-time observability.
 * @param {string} msg
 */
export function log(msg) {
  process.stderr.write(`[init_session] ${msg}\n`);
}

/**
 * Finds the absolute path to an executable binary across PATH.
 * @param {string} binName
 * @returns {string | null}
 */
export function findExecutable(binName) {
  const envPath = process.env.PATH || "";
  const pathDirs = envPath.split(path.delimiter);
  const extensions =
    process.platform === "win32" ? (process.env.PATHEXT || ".EXE;.CMD;.BAT").split(";") : [""];

  for (const dir of pathDirs) {
    if (!dir) continue;
    for (const ext of extensions) {
      const fullPath = path.join(dir, binName + ext);
      try {
        fs.accessSync(fullPath, fs.constants.X_OK);
        return fullPath;
      } catch {
        // Continue searching
      }
    }
  }
  return null;
}

/**
 * Ensures the bundled jl data-product plugin is installed and operational.
 * Must run before any other step. Fails hard if jl is missing or install fails.
 * Always installs from packages/*.tgz — no fast-path skip.
 */
export function installPlugin() {
  const jlBin = findExecutable("jl");
  if (!jlBin) {
    console.log(
      JSON.stringify({
        success: false,
        error: "jl CLI not found on PATH — install it before running this script.",
      }),
    );
    process.exit(1);
  }

  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const packagesDir = path.resolve(__dirname, "..", "packages");

  let tgzFiles = [];
  if (fs.existsSync(packagesDir)) {
    tgzFiles = fs
      .readdirSync(packagesDir)
      .filter((file) => file.endsWith(".tgz"))
      .sort()
      .map((file) => path.resolve(packagesDir, file));
  }

  if (tgzFiles.length === 0) {
    console.log(
      JSON.stringify({
        success: false,
        error: `No .tgz plugin package found in ${packagesDir}`,
      }),
    );
    process.exit(1);
  }

  // Pick the newest bundle (sorted lexicographically; semver filenames sort correctly)
  const packagePath = tgzFiles[tgzFiles.length - 1];
  log(`[PLUGIN INSTALL] Installing plugin from: ${packagePath}`);

  // jl plugin add installs local .tgz into the solution store (or global store)
  let result = spawnSync(jlBin, ["plugin", "add", packagePath], {
    encoding: "utf-8",
  });

  // Fallback to --global if executed outside a solution directory without solution.yaml
  if (
    result.status !== 0 &&
    `${result.stderr || ""}${result.stdout || ""}`.includes("solution.yaml")
  ) {
    result = spawnSync(jlBin, ["plugin", "add", packagePath, "--global"], {
      encoding: "utf-8",
    });
  }

  if (result.status !== 0) {
    const errorDetail = (result.stderr || "" || result.stdout || "").trim();
    console.log(
      JSON.stringify({
        success: false,
        error: `Plugin installation failed: ${errorDetail}`,
      }),
    );
    process.exit(1);
  }

  log("[PLUGIN INSTALL] Plugin installed successfully.");
}

/**
 * Step 1b Rule:
 * Given an approved name (CamelCase): insert a dash before each uppercase letter
 * that follows a lowercase letter, lowercase everything, append -data-product.
 * Verify result is all-lowercase, dashes only, ends with -data-product.
 * @param {string} camelStr
 * @returns {string}
 */
export function computeKebabName(camelStr) {
  let s = camelStr.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
  if (!s.endsWith("-data-product")) {
    s += "-data-product";
  }

  const isValid = /^[a-z0-9]+(-[a-z0-9]+)*-data-product$/.test(s);
  if (!isValid) {
    throw new Error(
      `Computed folder name '${s}' violates kebab-case rule (must be lowercase, dashes only, ending with -data-product)`,
    );
  }

  log(`[CHECK: NAME] Input: '${camelStr}' -> Folder: '${s}' (kebab-case validation: PASSED)`);
  return s;
}

/**
 * Generates an authentic Base36 application namespace from a Solution ID (c.bdc.<base36>).
 * If solutionId is provided, deterministically encodes it using Base36.
 * If omitted, generates a random UUID4 as fallback.
 * @param {string | null | undefined} solutionId
 * @returns {string}
 */
export function computeBase36Namespace(solutionId) {
  let n;
  if (solutionId) {
    const cleaned = solutionId.trim();
    let parsedHex = null;
    const stripped = cleaned
      .replace(/^urn:uuid:/i, "")
      .replace(/[{}]/g, "")
      .replace(/-/g, "");
    if (/^[0-9a-fA-F]+$/.test(stripped) && stripped.length > 0) {
      parsedHex = stripped;
    }

    if (parsedHex) {
      try {
        n = BigInt("0x" + parsedHex);
      } catch {
        // Fallback to SHA256 if BigInt parse fails
      }
    }

    if (n === undefined) {
      const h = crypto.createHash("sha256").update(cleaned, "utf-8").digest("hex").slice(0, 32);
      n = BigInt("0x" + h);
    }
  } else {
    const uHex = crypto.randomUUID().replace(/-/g, "");
    n = BigInt("0x" + uHex);
  }

  const chars = "0123456789abcdefghijklmnopqrstuvwxyz";
  let s = "";
  let current = n;
  const base = 36n;
  while (current > 0n) {
    const r = current % base;
    current = current / base;
    s = chars[Number(r)] + s;
  }
  const namespace = `c.bdc.${s}`;
  log(
    `[CHECK: NAMESPACE] Solution ID: '${solutionId ?? "None"}' -> Generated Base36 namespace: '${namespace}'`,
  );
  return namespace;
}

/**
 * Step 1b Rule:
 * source_dp_fqdns is constructed from search result: take id and append .minor.patch
 * from version (drop the major segment).
 * Example: id = sap.s4com:dataProduct:MeasurementDocument:v1, version = 1.9.9
 *          -> sap.s4com:dataProduct:MeasurementDocument:v1.9.9
 * Never use id alone or id + '.' + version verbatim.
 * @param {string} dpId
 * @param {string} version
 * @returns {string}
 */
export function computeVersionedFqdn(dpId, version) {
  const cleanId = dpId.trim();
  const cleanVer = version.trim();

  let fqdn;
  if (/:v\d+\.\d+\.\d+$/.test(cleanId)) {
    fqdn = cleanId;
  } else {
    const parts = cleanVer.split(".");
    if (parts.length >= 2) {
      const minorPatch = "." + parts.slice(1).join(".");
      if (/:v\d+$/.test(cleanId)) {
        fqdn = cleanId + minorPatch;
      } else {
        fqdn = `${cleanId}.${cleanVer}`;
      }
    } else {
      fqdn = `${cleanId}.${cleanVer}`;
    }
  }

  log(`[CHECK: FQDN] Source DP: '${cleanId}', Version: '${cleanVer}' -> Versioned FQDN: '${fqdn}'`);
  return fqdn;
}

/**
 * Before creating the new session folder, remove any empty directories under
 * assets/ that end with '-data-product' — including one matching the approved
 * folder_name. These are stale placeholders created by the specification skill
 * before the Technical Name was finalised. Uses fs.rmdirSync so non-empty
 * folders are silently skipped — safe by construction, and a non-empty match
 * still trips the collision gate downstream.
 * @param {string} workspaceDir
 */
export function cleanupEmptyPlaceholderFolders(workspaceDir) {
  const assetsDir = path.join(workspaceDir, "assets");
  if (!fs.existsSync(assetsDir)) {
    return;
  }
  try {
    if (!fs.statSync(assetsDir).isDirectory()) {
      return;
    }
  } catch {
    return;
  }

  let entries = [];
  try {
    entries = fs.readdirSync(assetsDir);
  } catch {
    return;
  }

  for (const entry of entries) {
    if (!entry.endsWith("-data-product")) {
      continue;
    }
    const candidate = path.join(assetsDir, entry);
    try {
      if (!fs.statSync(candidate).isDirectory()) {
        continue;
      }
      fs.rmdirSync(candidate); // only succeeds if empty
      log(`[CLEANUP] Removed empty placeholder folder: '${candidate}'`);
    } catch {
      log(`[CLEANUP] Skipped non-empty folder: '${candidate}'`);
    }
  }
}

/**
 * Step 1b Rule:
 * Check if <working_directory>/<folder_name> already exists.
 * Check if <working_directory>/assets/<folder_name> already exists.
 * If exists and overwrite is False, raise collision gate.
 * @param {string} workspaceDir
 * @param {string} folderName
 * @param {boolean} overwrite
 */
export function checkFolderCollisions(workspaceDir, folderName, overwrite) {
  const rootFolder = path.join(workspaceDir, folderName);
  const assetsFolder = path.join(workspaceDir, "assets", folderName);

  const rootExists = fs.existsSync(rootFolder);
  const assetsExists = fs.existsSync(assetsFolder);

  log(`[CHECK: COLLISION] Root collision '${rootFolder}': ${rootExists ? "EXISTS" : "CLEAN"}`);
  log(
    `[CHECK: COLLISION] Assets collision '${assetsFolder}': ${assetsExists ? "EXISTS" : "CLEAN"}`,
  );

  if ((rootExists || assetsExists) && !overwrite) {
    const existingPath = rootExists ? rootFolder : assetsFolder;
    const errMsg =
      `A folder named '${folderName}' already exists at '${existingPath}'. ` +
      "Pass --overwrite to overwrite it or propose a different Technical Name.";
    log(`[GATE: COLLISION FAILED] ${errMsg}`);
    console.log(
      JSON.stringify(
        {
          success: false,
          collision: true,
          folder_name: folderName,
          existing_path: existingPath,
          error: errMsg,
        },
        null,
        2,
      ),
    );
    process.exit(2);
  }

  if ((rootExists || assetsExists) && overwrite) {
    log(
      "[GATE: COLLISION] Folder exists but --overwrite was specified. Proceeding with overwrite.",
    );
  }
}

/**
 * Step 1b Mandatory Verification Gates (Before proceeding to Step 2):
 * 1. session_folder in context = <working_directory>/assets/<folder_name> (must be absolute path)
 * 2. <session_folder>/work/ directory exists
 * 3. .ddp_metadata.json exists inside <session_folder>/work/
 * 4. folder_name ends with -data-product
 * @param {string} sessionFolder
 * @param {string} workDir
 * @param {string} metadataPath
 * @param {string} folderName
 * @param {string} workspaceDir
 * @returns {object}
 */
export function verifyPreflightGates(
  sessionFolder,
  workDir,
  metadataPath,
  folderName,
  workspaceDir,
) {
  const expectedSessionFolder = path.resolve(workspaceDir, "assets", folderName);

  let workDirIsDir = false;
  try {
    workDirIsDir = fs.statSync(workDir).isDirectory();
  } catch {
    // Non-existent or not directory
  }

  let metadataValid = false;
  try {
    const stat = fs.statSync(metadataPath);
    metadataValid = stat.isFile() && stat.size > 0;
  } catch {
    // Non-existent or invalid file
  }

  const gate1 =
    path.resolve(sessionFolder) === expectedSessionFolder && path.isAbsolute(sessionFolder);
  const gate2 = workDirIsDir;
  const gate3 = metadataValid;
  const gate4 =
    folderName.endsWith("-data-product") &&
    /^[a-z0-9]+(-[a-z0-9]+)*-data-product$/.test(folderName);

  process.stderr.write("\n=======================================================\n");
  process.stderr.write(" STEP 1b PRE-FLIGHT VERIFICATION GATES\n");
  process.stderr.write("=======================================================\n");
  process.stderr.write(
    ` [Gate 1] session_folder in assets/    : ${gate1 ? "PASSED" : "FAILED"} (${sessionFolder})\n`,
  );
  process.stderr.write(
    ` [Gate 2] <session_folder>/work/ exists: ${gate2 ? "PASSED" : "FAILED"} (${workDir})\n`,
  );
  process.stderr.write(
    ` [Gate 3] .ddp_metadata.json exists   : ${gate3 ? "PASSED" : "FAILED"} (${metadataPath})\n`,
  );
  process.stderr.write(
    ` [Gate 4] folder_name ends with suffix: ${gate4 ? "PASSED" : "FAILED"} (${folderName})\n`,
  );
  process.stderr.write("=======================================================\n");

  const allPassed = gate1 && gate2 && gate3 && gate4;
  process.stderr.write(` OVERALL STEP 1b STATUS: ${allPassed ? "READY FOR STEP 2" : "FAILED"}\n`);
  process.stderr.write("=======================================================\n\n");

  if (!allPassed) {
    throw new Error("One or more Step 1b pre-flight verification gates failed.");
  }

  return {
    gate1_session_folder_valid: gate1,
    gate2_work_dir_exists: gate2,
    gate3_metadata_file_valid: gate3,
    gate4_folder_suffix_valid: gate4,
    all_passed: allPassed,
  };
}

/**
 * Prints usage and CLI help options.
 */
export function printUsage() {
  process.stderr.write(`usage: init_session.js [-h] --name NAME --source-dps SOURCE_DPS [--title TITLE]
                       [--short-desc SHORT_DESC] [--desc DESC]
                       [--responsible RESPONSIBLE] [--namespace NAMESPACE]
                       [--solution-id SOLUTION_ID]
                       [--workspace-dir WORKSPACE_DIR] [--overwrite]

Deterministic session initializer for Data Products (Step 1b).

options:
  -h, --help            show this help message and exit
  --name NAME           Technical Name in CamelCase (e.g. NetRevenuePerformance)
  --source-dps SOURCE_DPS
                        JSON array of source DPs: '[{"ordId":"...","version":"1.6.0"},...]'
  --title TITLE         Business Name (defaults to spaced Technical Name)
  --short-desc SHORT_DESC
                        Short description (max 255 chars)
  --desc DESC           Full description
  --responsible RESPONSIBLE
                        Responsible entity (default: customer:vendor:Customer)
  --namespace NAMESPACE
                        Optional pre-computed application namespace
  --solution-id SOLUTION_ID
                        Solution ID / UUID to compute the application namespace
  --workspace-dir WORKSPACE_DIR
                        Workspace root directory (default: current directory)
  --overwrite           Overwrite existing session folder if already present
`);
}

/**
 * Main command-line entrypoint.
 */
export function main() {
  let values;
  try {
    const parsed = parseArgs({
      options: {
        name: { type: "string" },
        "source-dps": { type: "string" },
        title: { type: "string" },
        "short-desc": { type: "string" },
        desc: { type: "string" },
        responsible: { type: "string", default: "customer:vendor:Customer" },
        namespace: { type: "string" },
        "solution-id": { type: "string" },
        "workspace-dir": { type: "string", default: process.cwd() },
        overwrite: { type: "boolean", default: false },
        help: { type: "boolean", short: "h", default: false },
      },
      allowPositionals: false,
    });
    values = parsed.values;
  } catch (err) {
    process.stderr.write(`init_session.js: error: ${err.message}\n`);
    printUsage();
    process.exit(2);
  }

  if (values.help) {
    printUsage();
    process.exit(0);
  }

  if (!values.name || !values["source-dps"]) {
    const missing = [];
    if (!values.name) missing.push("--name");
    if (!values["source-dps"]) missing.push("--source-dps");
    process.stderr.write(
      `init_session.js: error: the following arguments are required: ${missing.join(", ")}\n`,
    );
    process.exit(2);
  }

  const workspaceDir = path.resolve(values["workspace-dir"]);

  installPlugin();

  log(`Starting session initialization for workspace: '${workspaceDir}'`);

  // 1. Validate Technical Name (Rule: CamelCase, 1-70 chars)
  const techName = values.name.trim();
  if (!(techName.length >= 1 && techName.length <= 70 && /^[A-Z][A-Za-z0-9_]*$/.test(techName))) {
    const errMsg =
      `Invalid technical name '${techName}'. Must be CamelCase starting with an uppercase letter ` +
      `and between 1 and 70 characters (current length: ${techName.length}).`;
    log(`[ERROR] ${errMsg}`);
    console.log(JSON.stringify({ success: false, error: errMsg }));
    process.exit(1);
  }

  // 2. Derive Business Name / Title (Rule: Derived from Technical Name with spaces)
  const title = values.title?.trim() || techName.replace(/([a-z0-9])([A-Z])/g, "$1 $2");
  log(`[CHECK: TITLE] Business Name / Title: '${title}' (derived with spaces from '${techName}')`);

  // 3. Derive descriptions if not provided
  const shortDesc = values["short-desc"]?.trim() || `Analytics data product for ${title}.`;
  const desc =
    values.desc?.trim() || `This data product provides analytics and insights for ${title}.`;

  // 4. Folder name computation
  const folderName = computeKebabName(techName);

  // 5. Clean up empty placeholder folders, then check for collisions
  cleanupEmptyPlaceholderFolders(workspaceDir);
  checkFolderCollisions(workspaceDir, folderName, Boolean(values.overwrite));

  // 6. Namespace computation
  const namespace = values.namespace?.trim() || computeBase36Namespace(values["solution-id"]);

  // 7. Source DP FQDNs — parse JSON array, compute versioned FQDN for each
  let sourceDps;
  try {
    sourceDps = JSON.parse(values["source-dps"]);
    if (!Array.isArray(sourceDps) || sourceDps.length === 0) {
      throw new Error("--source-dps must be a non-empty JSON array");
    }
    for (const entry of sourceDps) {
      if (!entry.ordId || !entry.version) {
        throw new Error(`Each entry must have 'ordId' and 'version': ${JSON.stringify(entry)}`);
      }
    }
  } catch (err) {
    console.log(JSON.stringify({ success: false, error: `Invalid --source-dps: ${err.message}` }));
    process.exit(1);
  }
  const sourceFqdns = sourceDps.map((dp) => computeVersionedFqdn(dp.ordId, dp.version));

  // 8. Create directory structure: assets/<folder_name>/work
  const assetsDir = path.join(workspaceDir, "assets");
  const sessionFolder = path.join(assetsDir, folderName);
  const workDir = path.join(sessionFolder, "work");

  fs.mkdirSync(workDir, { recursive: true });
  log(`[EXEC: MKDIR] Created session work directory: '${workDir}'`);

  // 9. Construct .ddp_metadata.json
  const nowIso = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const metadata = {
    derived_dp_name: techName,
    source_dp_fqdns: sourceFqdns,
    applicationNamespace: namespace,
    created_at: nowIso,
    metadata_approved: true,
    header: {
      name: techName,
      title,
      description: desc,
      type: "derived",
      shortDescription: shortDesc,
      version: "1.0.0",
      applicationNamespace: namespace,
      responsible: values.responsible || "customer:vendor:Customer",
    },
  };

  const metadataPath = path.join(workDir, ".ddp_metadata.json");
  fs.writeFileSync(metadataPath, JSON.stringify(metadata, null, 2) + "\n", "utf-8");
  log(
    `[EXEC: WRITE] Wrote metadata file: '${metadataPath}' (${fs.statSync(metadataPath).size} bytes)`,
  );

  // 10. Sync specification folder name if a placeholder exists
  const specDir = path.join(workspaceDir, "specification");
  if (fs.existsSync(specDir)) {
    try {
      const entries = fs.readdirSync(specDir, { withFileTypes: true });
      for (const entry of entries) {
        if (
          entry.isDirectory() &&
          entry.name !== folderName &&
          entry.name.endsWith("-data-product")
        ) {
          const entryPath = path.join(specDir, entry.name);
          const targetSpecPath = path.join(specDir, folderName);
          if (!fs.existsSync(targetSpecPath)) {
            try {
              fs.renameSync(entryPath, targetSpecPath);
              log(
                `[EXEC: SPEC SYNC] Renamed placeholder 'specification/${entry.name}' -> 'specification/${folderName}'`,
              );
            } catch (e) {
              log(
                `[WARN: SPEC SYNC] Failed to rename spec placeholder '${entry.name}': ${e.message}`,
              );
            }
          } else {
            log(
              `[CHECK: SPEC SYNC] Target specification folder already exists at '${targetSpecPath}'`,
            );
          }
        }
      }
    } catch (err) {
      log(`[WARN: SPEC SYNC] Error reading specification directory: ${err.message}`);
    }
  }

  // 11. Run Pre-flight Gates Verification
  verifyPreflightGates(sessionFolder, workDir, metadataPath, folderName, workspaceDir);

  // 12. Output clean JSON to stdout
  console.log(
    JSON.stringify(
      {
        success: true,
        session_folder: sessionFolder,
      },
      null,
      2,
    ),
  );
}

const isDirectExecution =
  process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (isDirectExecution) {
  main();
}
