#!/usr/bin/env python3
"""Render the shared addon source (src/letsbot_connector) into one folder per
Odoo series (17.0/, 18.0/, 19.0/), i.e. the content of each Apps Store branch.

Python code is identical for every series (version differences are detected
at runtime: API-key expiry column, res.users group field name). Only XML /
manifest tokens differ:

  @@SERIES@@      -> 17.0 | 18.0 | 19.0          (manifest version prefix)
  @@LIST@@        -> tree (17.0) | list (18.0+)  (list view tag + view_mode)
  @@CRON_EXTRA@@  -> numbercall/doall on 17.0, nothing on 18.0+

Usage:  python3 build.py            # render all series
        python3 build.py --check    # fail if a rendered tree is stale
"""
import filecmp
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src", "letsbot_connector")
SERIES = ("17.0", "18.0", "19.0")
TEXT_EXT = (".py", ".xml", ".csv", ".html", ".rst", ".po", ".pot", ".md", ".txt")


def tokens(series):
    major = int(series.split(".")[0])
    return {
        "@@SERIES@@": series,
        "@@LIST@@": "tree" if major < 18 else "list",
        "@@CRON_EXTRA@@": ('        <field name="numbercall">-1</field>\n'
                           '        <field name="doall" eval="False"/>\n') if major < 18 else "",
    }


def render(series, dest_root):
    dest = os.path.join(dest_root, "letsbot_connector")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    for dirpath, dirnames, filenames in os.walk(SRC):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        rel = os.path.relpath(dirpath, SRC)
        out_dir = os.path.normpath(os.path.join(dest, rel))
        os.makedirs(out_dir, exist_ok=True)
        for name in filenames:
            if name.endswith(".pyc") or name == ".DS_Store":
                continue
            src_file, out_file = os.path.join(dirpath, name), os.path.join(out_dir, name)
            if name.endswith(TEXT_EXT):
                with open(src_file, encoding="utf-8") as fh:
                    content = fh.read()
                for token, value in tokens(series).items():
                    content = content.replace(token, value)
                if "@@" in content:
                    raise SystemExit("unrendered token in %s" % src_file)
                with open(out_file, "w", encoding="utf-8") as fh:
                    fh.write(content)
            else:
                shutil.copy2(src_file, out_file)
    for extra in ("LICENSE",):
        if os.path.exists(os.path.join(HERE, extra)):
            shutil.copy2(os.path.join(HERE, extra), os.path.join(dest_root, extra))


def same_tree(a, b):
    cmp = filecmp.dircmp(a, b, ignore=["__pycache__"])
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(same_tree(os.path.join(a, d), os.path.join(b, d)) for d in cmp.common_dirs)


def main():
    check = "--check" in sys.argv
    stale = []
    for series in SERIES:
        target = os.path.join(HERE, series)
        if check:
            with tempfile.TemporaryDirectory() as tmp:
                render(series, tmp)
                current = os.path.join(target, "letsbot_connector")
                if not os.path.isdir(current) or not same_tree(os.path.join(tmp, "letsbot_connector"), current):
                    stale.append(series)
        else:
            os.makedirs(target, exist_ok=True)
            render(series, target)
            print("rendered %s/letsbot_connector" % series)
    if stale:
        raise SystemExit("stale series: %s (run python3 build.py)" % ", ".join(stale))


if __name__ == "__main__":
    main()
