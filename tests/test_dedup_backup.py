import csv

import pytest

from dedup_backup import purge_from_csv, scan_duplicates


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_scan_finds_duplicate_by_content_with_different_name(tmp_path):
    source = tmp_path / "source"
    backup = tmp_path / "backup"
    source.mkdir()
    backup.mkdir()
    (source / "archive.txt").write_text("same content", encoding="utf-8")
    (backup / "renamed.txt").write_text("same content", encoding="utf-8")
    (backup / "unique.txt").write_text("unique content", encoding="utf-8")
    out_csv = tmp_path / "duplicates.csv"

    matched = scan_duplicates(str(source), str(backup), str(out_csv), verbose=False)

    rows = read_csv(out_csv)
    assert matched == 1
    assert len(rows) == 1
    assert rows[0]["backup_rel"] == "renamed.txt"
    assert rows[0]["source_rel"] == "archive.txt"


def test_purge_dry_run_does_not_delete_duplicate(tmp_path):
    source = tmp_path / "source"
    backup = tmp_path / "backup"
    source.mkdir()
    backup.mkdir()
    target = backup / "copy.txt"
    (source / "archive.txt").write_text("same content", encoding="utf-8")
    target.write_text("same content", encoding="utf-8")
    out_csv = tmp_path / "duplicates.csv"
    scan_duplicates(str(source), str(backup), str(out_csv), verbose=False)

    rows_read, ok, fail = purge_from_csv(str(backup), str(out_csv), yes=False, verbose=False)

    assert (rows_read, ok, fail) == (1, 1, 0)
    assert target.exists()


def test_purge_with_yes_deletes_duplicate(tmp_path):
    source = tmp_path / "source"
    backup = tmp_path / "backup"
    source.mkdir()
    backup.mkdir()
    target = backup / "copy.txt"
    (source / "archive.txt").write_text("same content", encoding="utf-8")
    target.write_text("same content", encoding="utf-8")
    out_csv = tmp_path / "duplicates.csv"
    scan_duplicates(str(source), str(backup), str(out_csv), verbose=False)

    rows_read, ok, fail = purge_from_csv(str(backup), str(out_csv), yes=True, verbose=False)

    assert (rows_read, ok, fail) == (1, 1, 0)
    assert not target.exists()


def test_purge_skips_csv_path_outside_backup_dir(tmp_path):
    backup = tmp_path / "backup"
    backup.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("do not delete", encoding="utf-8")
    csv_path = tmp_path / "malicious.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["digest", "size", "backup_path"])
        writer.writeheader()
        writer.writerow({"digest": "bad", "size": str(outside.stat().st_size), "backup_path": str(outside)})

    rows_read, ok, fail = purge_from_csv(str(backup), str(csv_path), verbose=False)

    assert (rows_read, ok, fail) == (1, 0, 1)
    assert outside.exists()


def test_scan_rejects_overlapping_source_and_backup(tmp_path):
    source = tmp_path / "source"
    backup = source / "backup"
    backup.mkdir(parents=True)

    with pytest.raises(ValueError, match="must not be the same or nested"):
        scan_duplicates(str(source), str(backup), str(tmp_path / "duplicates.csv"), verbose=False)
