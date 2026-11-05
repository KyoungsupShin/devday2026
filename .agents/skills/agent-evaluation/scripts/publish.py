#!/usr/bin/env python3
"""publish.py — atomically publish a staged aeval suite into the live aeval/ directory.

Usage:
    python3 skills/agent-evaluation/scripts/publish.py <output_dir>

<output_dir> is the agent's asset folder (…/assets/<asset-name>/). This moves the validated
suite from <output_dir>/aeval/.staging/ into <output_dir>/aeval/, in one deterministic step:

  1. require .staging/ with eval.yaml and testcases/ (refuse otherwise — nothing to publish)
  2. verify all template sources exist up front (fail fast before any mutation)
  3. create aeval/ and aeval/testcases/
  4. delete stale generated <id>.yaml in aeval/testcases/ that are not in the staged set
     (never the 000_pre_setup / zzz_post_teardown templates)
  5. copy eval.yaml into place (staging copy kept until rmtree); move every staged test case
  6. copy the static env templates and config.yaml with no-clobber (from this skill's templates/)
  7. remove .staging/

Zero dependencies (stdlib only). This exists because the publish sequence is mechanical and a
small model reliably drops the tail of a multi-step prose checklist — the same reason
structural validation is a script. Exit 0 on success, non-zero with a message otherwise.
"""
import os
import sys
import shutil
from pathlib import Path

TEMPLATES = ("000_pre_setup.yaml", "zzz_post_teardown.yaml")
CONFIG_TEMPLATE = "config.yaml"
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def main():
    if len(sys.argv) != 2:
        die("usage: publish.py <output_dir>  (the asset folder, …/assets/<asset-name>/)")
    output_dir = Path(sys.argv[1]).resolve()
    aeval = output_dir / "aeval"
    staging = aeval / ".staging"

    if not staging.is_dir():
        die(f"nothing to publish: {staging} does not exist")
    staged_eval = staging / "eval.yaml"
    staged_tc = staging / "testcases"
    if not staged_eval.exists():
        die(f"refusing to publish: {staged_eval} missing")
    if not staged_tc.is_dir():
        die(f"refusing to publish: {staged_tc} missing")

    missing_templates = [t for t in TEMPLATES if not (TEMPLATES_DIR / t).is_file()]
    if not (TEMPLATES_DIR / CONFIG_TEMPLATE).is_file():
        missing_templates.append(CONFIG_TEMPLATE)
    if missing_templates:
        die(f"template source missing in {TEMPLATES_DIR}: {', '.join(missing_templates)}", code=1)

    tc = aeval / "testcases"
    tc.mkdir(parents=True, exist_ok=True)

    staged_cases = sorted(p for p in staged_tc.glob("*.yaml"))
    staged_names = {p.name for p in staged_cases}

    # 3. delete stale generated cases (never templates)
    removed = []
    for p in tc.glob("*.yaml"):
        if p.name in TEMPLATES:
            continue
        if p.name not in staged_names:
            p.unlink()
            removed.append(p.name)

    # 4. copy eval.yaml; move staged test cases into place (overwrite)
    moved = []
    shutil.copy2(staged_eval, aeval / "eval.yaml"); moved.append("eval.yaml")
    for p in staged_cases:
        os.replace(p, tc / p.name); moved.append(f"testcases/{p.name}")

    # 5. copy static templates, no-clobber
    copied = []
    for t in TEMPLATES:
        dest = tc / t
        if not dest.exists():
            shutil.copyfile(TEMPLATES_DIR / t, dest); copied.append(t)

    cfg_dest = aeval / CONFIG_TEMPLATE
    if not cfg_dest.exists():
        shutil.copyfile(TEMPLATES_DIR / CONFIG_TEMPLATE, cfg_dest); copied.append(CONFIG_TEMPLATE)

    # 6. remove staging
    shutil.rmtree(staging, ignore_errors=True)

    print(f"published {len(moved)} file(s) to {aeval}")
    if removed:
        print(f"  removed stale: {', '.join(removed)}")
    if copied:
        print(f"  templates copied: {', '.join(copied)}")
    # sanity: all templates must now be present
    absent = [t for t in TEMPLATES if not (tc / t).exists()]
    if not cfg_dest.exists():
        absent.append(CONFIG_TEMPLATE)
    if absent:
        die(f"  publish incomplete — missing templates after copy: {', '.join(absent)}", code=1)
    print("  staging removed; publish complete")


if __name__ == "__main__":
    main()
