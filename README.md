# backup-dedup

> Backup directory deduplicator (by digest)

用 digest（雜湊）比對檔案內容，找出「備份目錄」中已存在於「原始目錄」的重複檔，輸出 CSV 清單，並可依 CSV 安全地刪除備份目錄中的重複檔。

即使檔名或路徑不同，只要內容相同，也會被判定為重複檔案。

> 適用情境：多次備份造成備份目錄堆出大量重複檔案，但只想保留原始目錄那份即可。

---

## Features

- 指定 `--source`（原始目錄）與 `--backup`（備份目錄）
- 用 **digest（預設 sha256）** 比對內容，檔名不同也能找出重複檔
- 輸出重複檔清單到 **CSV**
- 依 CSV 清單移除 **備份目錄** 的重複檔
- **預設 dry-run**：不會真的刪檔，必須加 `--yes` 才會執行刪除
- 刪除前安全檢查：
  - 路徑必須位於 `--backup` 目錄內
  - 預設會再做一次 size + digest 驗證，避免誤刪（可用 `--no-verify-hash` 關閉）
- 不需第三方套件，只使用 Python 標準函式庫

---

## Requirements

- Python 3.8+（建議 3.10+）
- 不需第三方套件

---

## Install

### Option A: 直接使用（建議）

把 `dedup_backup.py` 放到任意資料夾即可使用。

```bash
python dedup_backup.py --help
```

### Option B: 變成可執行

Linux/macOS:

```bash
chmod +x dedup_backup.py
./dedup_backup.py --help
```

Windows（PowerShell）：

```powershell
python .\dedup_backup.py --help
```

---

## Recommended Workflow

1. **先掃描**

   ```bash
   python dedup_backup.py scan --source "SRC" --backup "BAK" --out duplicates.csv
   ```

2. **打開 CSV 檢視**

3. **dry-run purge**

   ```bash
   python dedup_backup.py purge --backup "BAK" --csv duplicates.csv
   ```

4. **確認後真正刪除**

   ```bash
   python dedup_backup.py purge --backup "BAK" --csv duplicates.csv --yes
   ```

---

## Usage

程式提供兩個子命令：`scan` 與 `purge`。

### 1) Scan：掃描並輸出 CSV

```bash
python dedup_backup.py scan \
  --source "/path/to/source" \
  --backup "/path/to/backup" \
  --out "./duplicates.csv"
```

範例：

```bash
python dedup_backup.py scan \
  --source "$HOME/Pictures" \
  --backup "$HOME/OldBackup/Pictures" \
  --out "$HOME/duplicates.csv"
```

程式會：

- 遞迴掃描 `--source` 和 `--backup` 底下的普通檔案。
- 先用檔案大小分組，降低不必要的雜湊計算。
- 對大小相同的候選檔案計算 digest。
- 將備份目錄中已存在於原始目錄的檔案寫入 CSV。

可選參數：

- `--algo sha256|md5|blake2b|...`：指定雜湊算法（預設 `sha256`）
- `--follow-symlinks`：遍歷目錄時跟隨 symbolic link（預設不跟）
- `--all-matches`：若同一個 digest 在 source 內有多個檔案匹配，輸出全部（CSV 會變大）
- `--quiet`：減少 log

#### CSV 欄位說明

| 欄位 | 說明 |
| --- | --- |
| `digest` | 檔案內容雜湊（相同代表內容相同） |
| `size` | 檔案大小（bytes） |
| `backup_path` | 備份檔絕對路徑（候選刪除） |
| `backup_rel` | 相對於 backup 目錄的路徑 |
| `source_path` | 原始檔絕對路徑（保留） |
| `source_rel` | 相對於 source 目錄的路徑 |
| `match_count` | source 端匹配數量（搭配 `--all-matches` 會更有意義） |

CSV 範例：

```csv
digest,size,backup_path,backup_rel,source_path,source_rel,match_count
4e9c...,248102,/backup/photo-copy.jpg,photo-copy.jpg,/source/2024/photo.jpg,2024/photo.jpg,1
```

### 2) Purge：依 CSV 清單刪除（預設 dry-run）

先跑 dry-run 看看會刪哪些：

```bash
python dedup_backup.py purge \
  --backup "/path/to/backup" \
  --csv "./duplicates.csv"
```

範例：

```bash
python dedup_backup.py purge \
  --backup "$HOME/OldBackup/Pictures" \
  --csv "$HOME/duplicates.csv"
```

輸出中看到 `WOULD DELETE` 代表如果加上 `--yes`，該檔案會被刪除。

確定沒問題再真的刪：

```bash
python dedup_backup.py purge \
  --backup "/path/to/backup" \
  --csv "./duplicates.csv" \
  --yes
```

範例：

```bash
python dedup_backup.py purge \
  --backup "$HOME/OldBackup/Pictures" \
  --csv "$HOME/duplicates.csv" \
  --yes
```

可選參數：

- `--no-verify-hash`：刪除前不再重新算 digest（較快但風險較高）
- `--algo`：指定 CSV 使用的 hash 算法（預設 `sha256`）
- `--quiet`：減少 log

---

## Advanced Examples

### 使用不同雜湊演算法

掃描與刪除時必須使用同一個 `--algo`。

```bash
python dedup_backup.py scan \
  --source /data/main \
  --backup /data/backup \
  --out /tmp/duplicates-md5.csv \
  --algo md5

python dedup_backup.py purge \
  --backup /data/backup \
  --csv /tmp/duplicates-md5.csv \
  --algo md5
```

### 輸出所有來源匹配檔案

預設每個備份檔案只記錄第一個匹配的來源檔案。若想列出所有匹配來源，加上 `--all-matches`：

```bash
python dedup_backup.py scan \
  --source /data/main \
  --backup /data/backup \
  --out /tmp/duplicates-all.csv \
  --all-matches
```

注意：這可能讓 CSV 變大。`purge` 會依 `backup_path` 去重，所以同一個備份檔案即使在 CSV 中出現多列，也只會處理一次。

### 跟隨 symbolic link

預設不跟隨 symbolic link。若需要掃描 symbolic link 指向的檔案：

```bash
python dedup_backup.py scan \
  --source /data/main \
  --backup /data/backup \
  --out /tmp/duplicates.csv \
  --follow-symlinks
```

### 減少輸出訊息

```bash
python dedup_backup.py scan \
  --source /data/main \
  --backup /data/backup \
  --out /tmp/duplicates.csv \
  --quiet
```

```bash
python dedup_backup.py purge \
  --backup /data/backup \
  --csv /tmp/duplicates.csv \
  --quiet
```

### 跳過刪除前雜湊驗證

`purge` 預設會在刪除前再次檢查檔案大小與 digest，避免 CSV 產生後檔案內容已變更。若確定 CSV 與檔案狀態仍一致，可以跳過驗證：

```bash
python dedup_backup.py purge \
  --backup /data/backup \
  --csv /tmp/duplicates.csv \
  --no-verify-hash \
  --yes
```

不建議在不確定檔案狀態時使用此選項。

---

## How It Works

- 先依 **檔案大小（size）** 對 source 目錄做索引（避免每個檔都算 hash）
- 對 backup 檔案：
  - 找到 source 裡 size 相同的候選檔
  - 只對候選檔計算 digest，比對是否一致
- 產出 CSV 之後，`purge` 會依 CSV 清單處理刪除（預設再次驗證 size + digest）

---

## Safety Notes

- `purge` 預設 dry-run，不加 `--yes` 不會刪除檔案。
- `purge` 只會刪除位於 `--backup` 目錄底下的檔案，避免 CSV 被惡意或誤改導致刪到別處。
- 預設會重新算 digest 驗證內容一致後才刪，除非使用 `--no-verify-hash` 關閉。
- 若檔案不存在、無權限、驗證失敗或刪除失敗，會列為 skipped/failed。
- 此工具只會刪除備份目錄中出現在 CSV 的檔案，不會刪除原始目錄檔案。
- 若原始目錄或備份目錄內容在掃描後改變，建議重新掃描。

---

## Command Reference

### scan

```bash
python dedup_backup.py scan --source SOURCE --backup BACKUP --out CSV [options]
```

| 選項 | 說明 |
| --- | --- |
| `--source` | 要保留的原始目錄 |
| `--backup` | 要檢查並清理的備份目錄 |
| `--out` | 輸出的 CSV 路徑 |
| `--algo` | 雜湊演算法，預設 `sha256` |
| `--follow-symlinks` | 掃描時跟隨 symbolic link |
| `--all-matches` | 輸出所有匹配的來源檔案 |
| `--quiet` | 減少輸出訊息 |

### purge

```bash
python dedup_backup.py purge --backup BACKUP --csv CSV [options]
```

| 選項 | 說明 |
| --- | --- |
| `--backup` | 備份目錄，也是刪除安全邊界 |
| `--csv` | `scan` 產生的 CSV |
| `--algo` | CSV 使用的雜湊演算法，預設 `sha256` |
| `--no-verify-hash` | 刪除前不重新驗證 digest |
| `--yes` | 實際刪除檔案 |
| `--quiet` | 減少輸出訊息 |

---

## License

本專案採用 **GNU General Public License v3.0 或更新版本**（**GPL-3.0-or-later**）授權。授權標示可見於 `dedup_backup.py` 的 SPDX header；若專案包含 `LICENSE` 檔案，請以該檔案內容為準。
