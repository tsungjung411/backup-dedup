# backup-dedup
> Backup directory deduplicator (by digest)

用 digest（雜湊）比對檔案內容，找出「備份目錄」中已存在於「原始目錄」的重複檔，輸出 CSV 清單，並可依 CSV 安全地刪除備份目錄中的重複檔。

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

---

## Requirements

- Python 3.8+（建議 3.10+）
- 不需第三方套件

---

## Install

### Option A: 直接使用（建議）
把 `dedup_backup.py` 放到任意資料夾即可使用。

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

## Usage

程式提供兩個子命令：`scan` 與 `purge`。

### 1) Scan：掃描並輸出 CSV

```bash
python dedup_backup.py scan \
  --source "/path/to/source" \
  --backup "/path/to/backup" \
  --out "./duplicates.csv"
```

可選參數：

* `--algo sha256|md5|blake2b|...`：指定雜湊算法（預設 `sha256`）
* `--follow-symlinks`：遍歷目錄時跟隨 symbolic link（預設不跟）
* `--all-matches`：若同一個 digest 在 source 內有多個檔案匹配，輸出全部（CSV 會變大）
* `--quiet`：減少 log

#### CSV 欄位說明

| 欄位            | 說明                                     |
| ------------- | -------------------------------------- |
| `digest`      | 檔案內容雜湊（相同代表內容相同）                       |
| `size`        | 檔案大小（bytes）                            |
| `backup_path` | 備份檔絕對路徑（候選刪除）                          |
| `backup_rel`  | 相對於 backup 目錄的路徑                       |
| `source_path` | 原始檔絕對路徑（保留）                            |
| `source_rel`  | 相對於 source 目錄的路徑                       |
| `match_count` | source 端匹配數量（搭配 `--all-matches` 會更有意義） |

---

### 2) Purge：依 CSV 清單刪除（預設 dry-run）

先跑 dry-run 看看會刪哪些：

```bash
python dedup_backup.py purge \
  --backup "/path/to/backup" \
  --csv "./duplicates.csv"
```

確定沒問題再真的刪：

```bash
python dedup_backup.py purge \
  --backup "/path/to/backup" \
  --csv "./duplicates.csv" \
  --yes
```

可選參數：

* `--no-verify-hash`：刪除前不再重新算 digest（較快但風險較高）
* `--algo`：指定 CSV 使用的 hash 算法（預設 `sha256`）
* `--quiet`：減少 log

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

## How It Works

* 先依 **檔案大小（size）** 對 source 目錄做索引（避免每個檔都算 hash）
* 對 backup 檔案：

  * 找到 source 裡 size 相同的候選檔
  * 只對候選檔計算 digest，比對是否一致
* 產出 CSV 之後，`purge` 會依 CSV 清單處理刪除（預設再次驗證 size + digest）

---

## Safety Notes

* `purge` 只會刪除位於 `--backup` 目錄底下的檔案（避免 CSV 被惡意或誤改導致刪到別處）
* 預設會重新算 digest 驗證內容一致後才刪（除非你關掉 `--no-verify-hash`）

---

## License

本專案採用 **GNU General Public License v3.0 或更新版本**（**GPL-3.0-or-later**）授權。詳見 `LICENSE` 檔案。


