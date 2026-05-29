#!/usr/bin/env python3
"""MiraDocs — Cleanup Script (cross-platform).

Usage:
    python3 cleanup.py              — interactive menu
    python3 cleanup.py --packages   — remove .venv + node_modules only
    python3 cleanup.py --cache      — remove build/cache artifacts only
    python3 cleanup.py --all        — packages + cache (not data)
    python3 cleanup.py --data       — delete all user document data
    python3 cleanup.py --full       — everything (packages + cache + data)
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

# ── Colour helpers (disabled on Windows without ANSI support) ────────────────
_USE_COLOR = sys.stdout.isatty() and (os.name != "nt" or os.environ.get("WT_SESSION"))

def _c(code: str, msg: str) -> str:
    return f"\033[{code}m{msg}\033[0m" if _USE_COLOR else msg

def ok(msg):      print(_c("32", f"  ✔  {msg}"))
def warn(msg):    print(_c("33", f"  ⚠  {msg}"))
def info(msg):    print(_c("36", f"  ℹ  {msg}"))
def header(msg):  print(_c("1;36", f"\n══ {msg} ══"))
def removed(msg): print(_c("31", f"  ✘  Removed: {msg}"))


removed_count = 0

def remove(target: str):
    global removed_count
    p = ROOT / target
    if p.exists() or p.is_symlink():
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        removed(target)
        removed_count += 1


def remove_pycache():
    """Remove all __pycache__ and .pyc outside .venv and node_modules."""
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = Path(dirpath).relative_to(ROOT)
        parts = rel.parts
        if ".venv" in parts or "node_modules" in parts:
            dirnames.clear()
            continue
        if Path(dirpath).name == "__pycache__":
            shutil.rmtree(dirpath)
            dirnames.clear()
            continue
        for f in filenames:
            if f.endswith(".pyc"):
                (Path(dirpath) / f).unlink()


def do_packages():
    header("Installed Packages")
    remove(".venv")
    remove("frontend/node_modules")
    remove("frontend/package-lock.json")


def do_cache():
    header("Build / Cache Artifacts")
    remove("frontend/.next")
    remove("frontend/tsconfig.tsbuildinfo")
    remove(".pytest_cache")
    info("Removing __pycache__ directories …")
    remove_pycache()
    ok("Python caches cleared")


def do_data():
    header("User Data")
    print()
    warn("This will permanently delete all uploaded documents,")
    warn("parsed output, page images, vector indexes, and the registry database.")
    print()
    confirm = input("  Type 'delete' to confirm: ").strip()
    if confirm != "delete":
        info("Data deletion cancelled.")
        return
    for d in ("raw", "parsed", "page_images", "tables", "figures", "indexes", "reports"):
        dp = ROOT / "data" / d
        if dp.is_dir():
            for child in dp.iterdir():
                if child.name == ".gitkeep":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            removed(f"data/{d}/*")
            global removed_count
            removed_count += 1
    remove("data/registry.db")
    remove("data/registry.db-shm")
    remove("data/registry.db-wal")
    remove("data/llm_settings.json")


def interactive():
    print(_c("1;36", "\n  MiraDocs — Cleanup"))
    print("  What would you like to remove?\n")
    print("  1) Installed packages      (.venv, frontend/node_modules)")
    print("  2) Build / cache artifacts  (.next, __pycache__, .pytest_cache)")
    print("  3) Both 1 + 2               (full reset — re-run setup.py)")
    print("  4) User data                (documents, parsed output, registry.db)")
    print("  5) Everything               (1 + 2 + 4)")
    print("  q) Quit\n")
    choice = input("  Choice [1-5 / q]: ").strip()
    if choice == "1":
        do_packages()
    elif choice == "2":
        do_cache()
    elif choice == "3":
        do_packages(); do_cache()
    elif choice == "4":
        do_data()
    elif choice == "5":
        do_packages(); do_cache(); do_data()
    elif choice.lower() == "q":
        info("Nothing removed.")
        return
    else:
        print(_c("31", "  Invalid choice."))
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="MiraDocs cleanup utility")
    parser.add_argument("--packages", action="store_true", help="Remove .venv + node_modules")
    parser.add_argument("--cache", action="store_true", help="Remove build/cache artifacts")
    parser.add_argument("--all", action="store_true", help="Packages + cache")
    parser.add_argument("--data", action="store_true", help="Delete all user document data")
    parser.add_argument("--full", action="store_true", help="Everything")
    args = parser.parse_args()

    has_flag = args.packages or args.cache or args.all or args.data or args.full
    if not has_flag:
        interactive()
    else:
        if args.packages or args.all or args.full:
            do_packages()
        if args.cache or args.all or args.full:
            do_cache()
        if args.data or args.full:
            do_data()

    # Summary
    print(_c("1;36", "\n══════════════════════════════════════════"))
    if removed_count == 0:
        ok("Nothing to remove — workspace already clean.")
    else:
        ok(f"Done. {removed_count} item(s) removed.")
        if has_flag and (args.packages or args.all or args.full):
            print()
            info("Run python3 setup.py to reinstall dependencies.")
    print()


if __name__ == "__main__":
    main()
