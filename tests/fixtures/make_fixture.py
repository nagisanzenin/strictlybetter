#!/usr/bin/env python3
"""Copy a benchmark fixture into a fresh git repository with a baseline commit.

Usage:
    python3 make_fixture.py <pyfix|rustfix|greenfield> <dest_dir> [--force]

Copies the named fixture directory (excluding fixture-cards/, target/,
__pycache__/ and *.pyc), runs `git init -q -b main`, sets a local
user.name/user.email, commits everything as "fixture baseline", and prints two
lines: the absolute destination path, then the commit hash.

Refuses to overwrite an existing <dest_dir> unless --force is given.
"""

import argparse
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = ("pyfix", "rustfix", "greenfield")
EXCLUDED_DIRS = {"fixture-cards", "target", "__pycache__", ".git"}


def _ignore(_dir, names):
    return [n for n in names if n in EXCLUDED_DIRS or n.endswith(".pyc")]


def _git(dest, *args):
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=dest, check=True, capture_output=True, text=True,
    ).stdout.strip()


def make_fixture(name, dest, force=False):
    if name not in FIXTURES:
        raise SystemExit(f"unknown fixture {name!r}; choose from {', '.join(FIXTURES)}")
    src = HERE / name
    if not src.is_dir():
        raise SystemExit(f"fixture source missing: {src}")
    dest = pathlib.Path(dest).resolve()
    if dest.exists():
        if not force:
            raise SystemExit(f"refusing to overwrite existing {dest} (use --force)")
        if dest == HERE or HERE.is_relative_to(dest):
            raise SystemExit(f"refusing to remove {dest}: it contains the fixture sources")
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=_ignore)

    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "config", "user.name", "strictlybetter-fixture")
    _git(dest, "config", "user.email", "fixture@strictlybetter.invalid")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", "fixture baseline")
    commit = _git(dest, "rev-parse", "HEAD")
    return dest, commit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fixture", choices=FIXTURES)
    parser.add_argument("dest")
    parser.add_argument("--force", action="store_true", help="replace dest if it exists")
    args = parser.parse_args(argv)
    dest, commit = make_fixture(args.fixture, args.dest, force=args.force)
    print(dest)
    print(commit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
