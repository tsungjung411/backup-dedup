#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-

"""
dedup_backup.py

Goal:
- Scan "backup dir" files and find those that already exist in "source dir"
  by comparing digest (hash). Filenames may differ.
- Export duplicates to CSV.
- Remove duplicate files from backup dir based on CSV list (safe by default).

Usage examples:
  # 1) Scan and generate CSV
  python dedup_backup.py scan --source /path/src --backup /path/bak --out duplicates.csv

  # 2) Purge based on CSV (dry-run by default)
  python dedup_backup.py purge --backup /path/bak --csv duplicates.csv

  # 3) Actually delete
  python dedup_backup.py purge --backup /path/bak --csv duplicates.csv --yes

Notes:
- To reduce hashing cost, the scanner first groups source files by size,
  and only hashes candidates with the same size as a backup file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import stat
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class FileInfo:
    path: str
    size: int


def iter_regular_files(root: str, follow_symlinks: bool = False) -> Iterable[FileInfo]:
    """Yield regular files under root recursively."""
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p, follow_symlinks=follow_symlinks)
            except (FileNotFoundError, PermissionError, OSError):
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            yield FileInfo(path=p, size=st.st_size)


def file_digest(path: str, algo: str = "sha256", chunk_size: int = 1024 * 1024) -> str:
    """Compute digest for a file with streaming reads."""
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def safe_commonpath_is_parent(parent: str, child: str) -> bool:
    """Return True if child is under parent (path traversal protection)."""
    parent = os.path.abspath(parent)
    child = os.path.abspath(child)
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        return False


def scan_duplicates(
    source_dir: str,
    backup_dir: str,
    out_csv: str,
    algo: str = "sha256",
    follow_symlinks: bool = False,
    all_matches: bool = False,
    verbose: bool = True,
) -> int:
    """
    Scan backup_dir files and find duplicates that exist in source_dir by digest.

    CSV columns:
      digest, size, backup_path, backup_rel, source_path, source_rel, match_count
    """
    source_dir = os.path.abspath(source_dir)
    backup_dir = os.path.abspath(backup_dir)
    out_csv = os.path.abspath(out_csv)

    # 1) Index source by size -> list of FileInfo
    source_by_size: Dict[int, List[FileInfo]] = {}
    src_files = list(iter_regular_files(source_dir, follow_symlinks=follow_symlinks))
    for fi in src_files:
        source_by_size.setdefault(fi.size, []).append(fi)

    # Cache for source file digests
    src_digest_cache: Dict[str, str] = {}

    def get_src_digest(p: str) -> Optional[str]:
        if p in src_digest_cache:
            return src_digest_cache[p]
        try:
            d = file_digest(p, algo=algo)
        except (FileNotFoundError, PermissionError, OSError):
            return None
        src_digest_cache[p] = d
        return d

    bak_files = list(iter_regular_files(backup_dir, follow_symlinks=follow_symlinks))
    total_bak = len(bak_files)
    dup_rows: List[Dict[str, str]] = []

    scanned = 0
    matched = 0

    for bfi in bak_files:
        scanned += 1
        if verbose and scanned % 200 == 0:
            print(f"[scan] processed {scanned}/{total_bak} backup files...", file=sys.stderr)

        candidates = source_by_size.get(bfi.size)
        if not candidates:
            continue

        try:
            b_digest = file_digest(bfi.path, algo=algo)
        except (FileNotFoundError, PermissionError, OSError):
            continue

        src_matches: List[str] = []
        for sfi in candidates:
            sd = get_src_digest(sfi.path)
            if sd is None:
                continue
            if sd == b_digest:
                src_matches.append(sfi.path)
                if not all_matches:
                    break

        if not src_matches:
            continue

        matched += 1

        # Write one row per backup file; if all_matches True, output multiple rows.
        if all_matches:
            for sp in src_matches:
                dup_rows.append(
                    {
                        "digest": b_digest,
                        "size": str(bfi.size),
                        "backup_path": bfi.path,
                        "backup_rel": os.path.relpath(bfi.path, backup_dir),
                        "source_path": sp,
                        "source_rel": os.path.relpath(sp, source_dir),
                        "match_count": str(len(src_matches)),
                    }
                )
        else:
            sp = src_matches[0]
            dup_rows.append(
                {
                    "digest": b_digest,
                    "size": str(bfi.size),
                    "backup_path": bfi.path,
                    "backup_rel": os.path.relpath(bfi.path, backup_dir),
                    "source_path": sp,
                    "source_rel": os.path.relpath(sp, source_dir),
                    "match_count": str(len(src_matches)),
                }
            )

    # 2) Output CSV
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["digest", "size", "backup_path", "backup_rel", "source_path", "source_rel", "match_count"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in dup_rows:
            w.writerow(r)

    if verbose:
        print(f"[scan] source files indexed: {len(src_files)}", file=sys.stderr)
        print(f"[scan] backup files scanned: {total_bak}", file=sys.stderr)
        print(f"[scan] duplicates found (backup files): {matched}", file=sys.stderr)
        print(f"[scan] CSV written: {out_csv}", file=sys.stderr)

    return matched


def purge_from_csv(
    backup_dir: str,
    csv_path: str,
    yes: bool = False,
    verify_hash: bool = True,
    algo: str = "sha256",
    verbose: bool = True,
) -> Tuple[int, int, int]:
    """
    Delete backup files listed in CSV.

    Returns: (rows_read, delete_ok, delete_skip_or_fail)
    """
    backup_dir = os.path.abspath(backup_dir)
    csv_path = os.path.abspath(csv_path)

    rows_read = 0
    ok = 0
    fail = 0

    # Deduplicate by backup_path (CSV might contain multiple rows if all_matches was used)
    targets: Dict[str, Dict[str, str]] = {}

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        required = {"digest", "size", "backup_path"}
        if not required.issubset(set(r.fieldnames or [])):
            raise ValueError(f"CSV missing required columns: {required}")
        for row in r:
            rows_read += 1
            bp = row["backup_path"]
            if bp:
                targets[bp] = row

    if verbose:
        mode = "DELETE" if yes else "DRY-RUN"
        print(f"[purge] mode: {mode}", file=sys.stderr)
        print(f"[purge] unique targets from CSV: {len(targets)} (rows read: {rows_read})", file=sys.stderr)

    for bp, row in targets.items():
        bp_abs = os.path.abspath(bp)

        # Safety: must be inside backup_dir
        if not safe_commonpath_is_parent(backup_dir, bp_abs):
            fail += 1
            if verbose:
                print(f"[purge] SKIP (outside backup_dir): {bp_abs}", file=sys.stderr)
            continue

        if not os.path.exists(bp_abs):
            fail += 1
            if verbose:
                print(f"[purge] SKIP (missing): {bp_abs}", file=sys.stderr)
            continue

        # Optional verification (digest + size)
        if verify_hash:
            try:
                st = os.stat(bp_abs)
                size_ok = str(st.st_size) == row["size"]
                digest_ok = file_digest(bp_abs, algo=algo) == row["digest"]
                if not (size_ok and digest_ok):
                    fail += 1
                    if verbose:
                        print(f"[purge] SKIP (verify failed): {bp_abs}", file=sys.stderr)
                    continue
            except (PermissionError, OSError, FileNotFoundError):
                fail += 1
                if verbose:
                    print(f"[purge] SKIP (verify error): {bp_abs}", file=sys.stderr)
                continue

        if yes:
            try:
                os.remove(bp_abs)
                ok += 1
                if verbose:
                    print(f"[purge] DELETED: {bp_abs}", file=sys.stderr)
            except (PermissionError, OSError, FileNotFoundError):
                fail += 1
                if verbose:
                    print(f"[purge] FAIL (delete): {bp_abs}", file=sys.stderr)
        else:
            ok += 1
            if verbose:
                print(f"[purge] WOULD DELETE: {bp_abs}", file=sys.stderr)

    if verbose:
        print(f"[purge] success: {ok}, skipped/failed: {fail}", file=sys.stderr)

    return rows_read, ok, fail


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dedup_backup.py",
        description="Find and remove duplicate files in backup dir that already exist in source dir (by digest).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("scan", help="Scan backup dir and write duplicate list to CSV.")
    ps.add_argument("--source", required=True, help="Source directory (the one you want to keep).")
    ps.add_argument("--backup", required=True, help="Backup directory (will be cleaned).")
    ps.add_argument("--out", required=True, help="Output CSV path.")
    ps.add_argument("--algo", default="sha256", help="Hash algorithm (default: sha256).")
    ps.add_argument("--follow-symlinks", action="store_true", help="Follow symlinks during directory walk.")
    ps.add_argument("--all-matches", action="store_true", help="Write all matching source files (can enlarge CSV).")
    ps.add_argument("--quiet", action="store_true", help="Less logging.")

    pp = sub.add_parser("purge", help="Delete backup files listed in CSV (dry-run by default).")
    pp.add_argument("--backup", required=True, help="Backup directory (safety boundary).")
    pp.add_argument("--csv", required=True, help="CSV path generated by scan.")
    pp.add_argument("--algo", default="sha256", help="Hash algorithm used in CSV (default: sha256).")
    pp.add_argument("--no-verify-hash", action="store_true", help="Skip digest verification before deleting.")
    pp.add_argument("--yes", action="store_true", help="Actually delete files. Without this, it's dry-run.")
    pp.add_argument("--quiet", action="store_true", help="Less logging.")

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "scan":
        verbose = not args.quiet
        scan_duplicates(
            source_dir=args.source,
            backup_dir=args.backup,
            out_csv=args.out,
            algo=args.algo,
            follow_symlinks=args.follow_symlinks,
            all_matches=args.all_matches,
            verbose=verbose,
        )
        return 0

    if args.cmd == "purge":
        verbose = not args.quiet
        purge_from_csv(
            backup_dir=args.backup,
            csv_path=args.csv,
            yes=args.yes,
            verify_hash=(not args.no_verify_hash),
            algo=args.algo,
            verbose=verbose,
        )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
