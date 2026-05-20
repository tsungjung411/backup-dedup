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


__version__ = "v1.0.5"


@dataclass(frozen=True)
class FileInfo:
    path: str
    size: int


def iter_regular_files(
    root: str,
    follow_symlinks: bool = False,
) -> Iterable[FileInfo]:
    """Yield regular files under root recursively."""
    root = os.path.abspath(root)
    # Walk each directory under the requested root.
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # Visit each file name found in the current directory.
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p, follow_symlinks=follow_symlinks)
            except (FileNotFoundError, PermissionError, OSError):
                continue
            # Skip anything that is not a regular file.
            if not stat.S_ISREG(st.st_mode):
                continue
            yield FileInfo(path=p, size=st.st_size)


def file_digest(
    path: str,
    algo: str = "sha256",
    chunk_size: int = 1024 * 1024,
) -> str:
    """Compute digest for a file with streaming reads."""
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        # Read the file in chunks to avoid loading it all at once.
        while True:
            chunk = f.read(chunk_size)
            # Stop when the stream has no more bytes.
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def validate_hash_algorithm(algo: str) -> None:
    """Raise ValueError when the requested hash algorithm is unavailable."""
    try:
        hashlib.new(algo)
    except ValueError as exc:
        raise ValueError(f"unsupported hash algorithm: {algo}") from exc


def validate_directory(path: str, label: str) -> None:
    """Raise ValueError when path is not an existing directory."""
    if not os.path.isdir(path):
        raise ValueError(f"{label} directory does not exist or is not a directory: {path}")


def validate_file(path: str, label: str) -> None:
    """Raise ValueError when path is not an existing file."""
    if not os.path.isfile(path):
        raise ValueError(f"{label} file does not exist or is not a file: {path}")


def safe_commonpath_is_parent(parent: str, child: str) -> bool:
    """Return True if child is under parent (path traversal protection)."""
    parent = os.path.realpath(parent)
    child = os.path.realpath(child)
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        return False


def paths_overlap(path_a: str, path_b: str) -> bool:
    """Return True if two paths are equal or one contains the other."""
    path_a = os.path.realpath(path_a)
    path_b = os.path.realpath(path_b)
    try:
        common = os.path.commonpath([path_a, path_b])
    except ValueError:
        return False
    return common == path_a or common == path_b


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

    validate_hash_algorithm(algo)
    validate_directory(source_dir, "source")
    validate_directory(backup_dir, "backup")

    if paths_overlap(source_dir, backup_dir):
        raise ValueError("source and backup directories must not be the same or nested")

    # 1) Index source by size -> list of FileInfo
    source_by_size: Dict[int, List[FileInfo]] = {}
    src_files = list(iter_regular_files(source_dir, follow_symlinks=follow_symlinks))
    # Group source files by size before hashing.
    for fi in src_files:
        source_by_size.setdefault(fi.size, []).append(fi)

    # Cache for source file digests
    src_digest_cache: Dict[str, str] = {}

    def get_src_digest(p: str) -> Optional[str]:
        # Reuse source digests that were already computed.
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

    # Check each backup file against same-size source files.
    for bfi in bak_files:
        scanned += 1
        # Show progress every 200 files when logging is enabled.
        if verbose and scanned % 200 == 0:
            print(f"[scan] processed {scanned}/{total_bak} backup files...", file=sys.stderr)

        if not safe_commonpath_is_parent(backup_dir, bfi.path):
            continue

        candidates = source_by_size.get(bfi.size)
        # Files with unique sizes cannot be content duplicates.
        if not candidates:
            continue

        try:
            b_digest = file_digest(bfi.path, algo=algo)
        except (FileNotFoundError, PermissionError, OSError):
            continue

        src_matches: List[str] = []
        # Compare the backup digest with each same-size source file.
        for sfi in candidates:
            sd = get_src_digest(sfi.path)
            # Ignore source files that could not be hashed.
            if sd is None:
                continue
            # Record the source file when the content digest matches.
            if sd == b_digest:
                src_matches.append(sfi.path)
                # Stop early unless the caller wants every match.
                if not all_matches:
                    break

        # Skip backup files that were not found in the source.
        if not src_matches:
            continue

        matched += 1

        # Write one row per backup file.
        # With all_matches, output multiple source rows.
        # Emit one row for each matching source file.
        if all_matches:
            # Store every source path that has the same digest.
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
        # Write each duplicate finding as one CSV row.
        for r in dup_rows:
            w.writerow(r)

    # Print scan totals when logging is enabled.
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

    validate_hash_algorithm(algo)
    validate_directory(backup_dir, "backup")
    validate_file(csv_path, "CSV")

    rows_read = 0
    ok = 0
    fail = 0

    # Deduplicate by backup_path.
    # all_matches can create multiple rows for one backup file.
    targets: Dict[str, Dict[str, str]] = {}

    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            r = csv.DictReader(f, strict=True)
            required = {"digest", "size", "backup_path"}
            # Ensure the CSV contains the columns needed for purge.
            if not required.issubset(set(r.fieldnames or [])):
                missing = ", ".join(sorted(required - set(r.fieldnames or [])))
                raise ValueError(f"CSV missing required columns: {missing}")
            # Read every CSV row and keep unique backup paths only.
            for row in r:
                rows_read += 1
                bp = row["backup_path"]
                # Ignore rows without a backup path.
                if bp:
                    targets[bp] = row
    except csv.Error as exc:
        raise ValueError(f"invalid CSV: {csv_path}: {exc}") from exc

    # Print purge mode and target count when logging is enabled.
    if verbose:
        mode = "DELETE" if yes else "DRY-RUN"
        print(f"[purge] mode: {mode}", file=sys.stderr)
        print(f"[purge] unique targets from CSV: {len(targets)} (rows read: {rows_read})", file=sys.stderr)

    # Process each unique backup file listed in the CSV.
    for bp, row in targets.items():
        bp_abs = os.path.abspath(bp)

        # Safety: must be inside backup_dir
        # Reject CSV paths that point outside the backup directory.
        if not safe_commonpath_is_parent(backup_dir, bp_abs):
            fail += 1
            # Report skipped paths when logging is enabled.
            if verbose:
                print(f"[purge] SKIP (outside backup_dir): {bp_abs}", file=sys.stderr)
            continue

        # Skip rows whose backup file no longer exists.
        if not os.path.exists(bp_abs):
            fail += 1
            # Report missing files when logging is enabled.
            if verbose:
                print(f"[purge] SKIP (missing): {bp_abs}", file=sys.stderr)
            continue

        # Optional verification (digest + size)
        # Recheck file identity before deletion unless disabled.
        if verify_hash:
            try:
                st = os.stat(bp_abs)
                size_ok = str(st.st_size) == row["size"]
                digest_ok = file_digest(bp_abs, algo=algo) == row["digest"]
                # Skip the file if it no longer matches the CSV row.
                if not (size_ok and digest_ok):
                    fail += 1
                    # Report verify failures when logging is enabled.
                    if verbose:
                        print(f"[purge] SKIP (verify failed): {bp_abs}", file=sys.stderr)
                    continue
            except (PermissionError, OSError, FileNotFoundError):
                fail += 1
                # Report verification errors when logging is enabled.
                if verbose:
                    print(f"[purge] SKIP (verify error): {bp_abs}", file=sys.stderr)
                continue

        # Delete only when the caller explicitly passed --yes.
        if yes:
            try:
                os.remove(bp_abs)
                ok += 1
                # Report deleted files when logging is enabled.
                if verbose:
                    print(f"[purge] DELETED: {bp_abs}", file=sys.stderr)
            except (PermissionError, OSError, FileNotFoundError):
                fail += 1
                # Report deletion errors when logging is enabled.
                if verbose:
                    print(f"[purge] FAIL (delete): {bp_abs}", file=sys.stderr)
        else:
            ok += 1
            # Report dry-run targets when logging is enabled.
            if verbose:
                print(f"[purge] WOULD DELETE: {bp_abs}", file=sys.stderr)

    # Print final purge totals when logging is enabled.
    if verbose:
        print(f"[purge] success: {ok}, skipped/failed: {fail}", file=sys.stderr)

    return rows_read, ok, fail


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dedup_backup.py",
        description="Find and remove duplicate files in backup dir that already exist in source dir (by digest).",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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

    # Dispatch the scan subcommand.
    if args.cmd == "scan":
        verbose = not args.quiet
        try:
            scan_duplicates(
                source_dir=args.source,
                backup_dir=args.backup,
                out_csv=args.out,
                algo=args.algo,
                follow_symlinks=args.follow_symlinks,
                all_matches=args.all_matches,
                verbose=verbose,
            )
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        return 0

    # Dispatch the purge subcommand.
    if args.cmd == "purge":
        verbose = not args.quiet
        try:
            purge_from_csv(
                backup_dir=args.backup,
                csv_path=args.csv,
                yes=args.yes,
                verify_hash=(not args.no_verify_hash),
                algo=args.algo,
                verbose=verbose,
            )
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        return 0

    return 2


# Run the CLI entry point when executed as a script.
if __name__ == "__main__":
    raise SystemExit(main())
