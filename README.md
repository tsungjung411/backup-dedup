# backup-dedup

你是不是也有好幾份手機備份？

一開始只是怕照片不見，所以先備一份。換手機時再備一份。整理硬碟時又把整包照片複製到另一個資料夾。幾年下來，硬碟裡可能出現這種狀況：

- `Phone_Backup_2021`
- `iPhone照片_舊`
- `DCIM_整理前`
- `Google Photos 匯出`
- `已歸檔照片`

每一份備份涵蓋的時間區段都不太一樣。有些只有 2020 年以前，有些多了 2021 到 2023，有些又混著截圖、影片、通訊軟體下載圖。你知道裡面一定有很多重複檔，但要一張一張打開確認，太花時間。

更麻煩的是，歸檔後檔名可能早就變了：

- 原本手機裡叫 `IMG_4821.JPG`
- 備份工具匯出後叫 `20210318_144012.jpg`
- 你整理後又改成 `20210318-東京旅行-上野公園.jpg`

檔名不同，不代表照片不同。用檔名找重複檔，很容易漏掉；用眼睛檢查，又很勞累。

`dedup_backup.py` 解決的是這件事：它不靠檔名判斷，而是比對檔案內容。只要內容相同，即使檔名、路徑、資料夾結構都不一樣，也能找出來。

---

## 這支工具適合做什麼？

你可以先把「已經整理好、想保留的照片資料夾」當成 `source`，再把「還沒整理、想清掉重複檔的舊備份」當成 `backup`。

程式會掃描 `backup` 裡的檔案，找出哪些其實已經存在於 `source`。找到後先輸出成 CSV 清單，讓你可以自己檢查；確認沒問題後，再依照 CSV 清單刪除 `backup` 裡的重複檔。

簡單說：

- `source`：你信任的歸檔區，這裡的檔案會保留
- `backup`：待清理的舊備份，這裡的重複檔會被列出來
- `CSV`：重複檔清單，讓你先看過再決定要不要刪

這很適合用在手機照片、影片、相機記憶卡備份、雲端相簿匯出檔等情境。

---

## 它怎麼避免誤判？

`dedup_backup.py` 使用 digest，也就是檔案內容的雜湊值來比對。預設使用 `sha256`。

它不是看檔名，也不是看修改時間。只要兩個檔案的內容完全一樣，就會被判定為相同檔案。反過來說，就算檔名看起來很像，只要內容不同，也不會被當成同一個檔案。

刪除也不是一開始就真的刪。流程預設分成兩段：

1. 先掃描並產生 CSV。
2. 再依 CSV 做 dry-run，確認會刪哪些檔案。
3. 最後你明確加上 `--yes`，才會真的刪除。

而且刪除前預設還會重新檢查檔案大小與 digest，避免 CSV 產生後檔案已經被改動。

---

## 推薦使用流程

假設：

- `D:\Photos\Archive` 是你已整理好的照片歸檔區
- `D:\Photos\OldPhoneBackup` 是你想清理的舊手機備份

### 1. 掃描重複檔

```powershell
python .\dedup_backup.py scan `
  --source "D:\Photos\Archive" `
  --backup "D:\Photos\OldPhoneBackup" `
  --out ".\duplicates.csv"
```

這一步不會刪除任何檔案，只會產生 `duplicates.csv`。

### 2. 打開 CSV 檢查

CSV 會列出：

- 舊備份裡哪個檔案是重複的
- 它在歸檔區對應到哪個檔案
- 檔案大小與 digest

你可以用 Excel、LibreOffice Calc、文字編輯器或任何 CSV 工具打開。

### 3. 先 dry-run

```powershell
python .\dedup_backup.py purge `
  --backup "D:\Photos\OldPhoneBackup" `
  --csv ".\duplicates.csv"
```

沒有加 `--yes` 時，程式只會顯示 `WOULD DELETE`，代表「如果真的執行，會刪這些檔案」。這一步仍然不會刪檔。

### 4. 確認後才真的刪除

```powershell
python .\dedup_backup.py purge `
  --backup "D:\Photos\OldPhoneBackup" `
  --csv ".\duplicates.csv" `
  --yes
```

加上 `--yes` 後，才會刪除 CSV 裡列出的 `backup` 重複檔。

---

## 安裝需求

- Python 3.8+，建議 Python 3.10+
- 不需要第三方套件

確認能執行：

```bash
python dedup_backup.py --help
python dedup_backup.py --version
```

查看各功能的完整參數：

```bash
python dedup_backup.py scan --help
python dedup_backup.py purge --help
```

Linux/macOS 也可以設成可執行：

```bash
chmod +x dedup_backup.py
./dedup_backup.py --help
```

---

## 指令說明

程式有兩個子命令：

- `scan`：掃描 `backup`，找出已存在於 `source` 的重複檔，輸出 CSV
- `purge`：依 CSV 清單刪除 `backup` 裡的重複檔，預設 dry-run

### scan

```bash
python dedup_backup.py scan \
  --source "/path/to/archive" \
  --backup "/path/to/old-backup" \
  --out "./duplicates.csv"
```

必要參數：

| 參數 | 說明 |
| --- | --- |
| `--source` | 要保留的來源目錄，例如已整理好的照片歸檔區 |
| `--backup` | 要檢查並清理的備份目錄 |
| `--out` | 輸出的 CSV 路徑 |

可選參數：

| 參數 | 說明 |
| --- | --- |
| `--algo` | 指定雜湊演算法，預設 `sha256`。常見可用值：`sha256`、`sha1`、`md5`、`blake2b`、`blake2s` |
| `--follow-symlinks` | 掃描「連到其他位置的檔案或資料夾入口」，也就是 symbolic link。一般手機照片備份通常不需要 |
| `--all-matches` | source 裡若有多個相同內容檔案，全部寫入 CSV |
| `--quiet` | 減少輸出訊息 |

### purge

```bash
python dedup_backup.py purge \
  --backup "/path/to/old-backup" \
  --csv "./duplicates.csv"
```

必要參數：

| 參數 | 說明 |
| --- | --- |
| `--backup` | 安全邊界，只有這個目錄內的檔案會被處理 |
| `--csv` | `scan` 產生的 CSV |

可選參數：

| 參數 | 說明 |
| --- | --- |
| `--yes` | 真的刪除檔案；沒加就是 dry-run |
| `--algo` | CSV 使用的雜湊演算法，預設 `sha256`。必須和 `scan` 時使用的演算法相同 |
| `--no-verify-hash` | 刪除前不重新驗證 digest，較快但風險較高 |
| `--quiet` | 減少輸出訊息 |

---

## CSV 欄位

| 欄位 | 說明 |
| --- | --- |
| `digest` | 檔案內容雜湊 |
| `size` | 檔案大小，單位 bytes |
| `backup_path` | 備份檔絕對路徑，這是候選刪除目標 |
| `backup_rel` | 相對於 backup 目錄的路徑 |
| `source_path` | source 裡對應到的檔案絕對路徑，這份會保留 |
| `source_rel` | 相對於 source 目錄的路徑 |
| `match_count` | source 端匹配數量 |

範例：

```csv
digest,size,backup_path,backup_rel,source_path,source_rel,match_count
4e9c...,248102,/backup/IMG_4821.JPG,IMG_4821.JPG,/archive/2021/東京旅行-上野公園.jpg,2021/東京旅行-上野公園.jpg,1
```

---

## 進階用法

### 使用不同雜湊演算法

掃描與刪除時要使用同一個 `--algo`。

常見可用值：

| 演算法 | 說明 |
| --- | --- |
| `sha256` | 預設值，適合一般使用 |
| `sha1` | 較舊的 SHA-1，通常不建議優先選 |
| `md5` | 速度較快，但抗碰撞性較弱；只建議用於非安全用途的初步比對 |
| `blake2b` | 現代雜湊演算法，通常速度與安全性表現都不錯 |
| `blake2s` | BLAKE2 的另一個版本，適合較小平台或特定需求 |

實際可用演算法取決於你的 Python/OpenSSL 環境。若不確定，直接使用預設的 `sha256`。

```bash
python dedup_backup.py scan \
  --source /data/archive \
  --backup /data/old-backup \
  --out /tmp/duplicates-md5.csv \
  --algo md5

python dedup_backup.py purge \
  --backup /data/old-backup \
  --csv /tmp/duplicates-md5.csv \
  --algo md5
```

### 列出所有 source 匹配檔

預設每個 backup 檔案只記錄第一個匹配到的 source 檔案。若想列出全部：

```bash
python dedup_backup.py scan \
  --source /data/archive \
  --backup /data/old-backup \
  --out /tmp/duplicates-all.csv \
  --all-matches
```

`purge` 會依 `backup_path` 去重，所以同一個 backup 檔案即使在 CSV 中出現多列，也只會處理一次。

### 掃描連到其他位置的檔案(symbolic link)

預設只掃描資料夾裡實際存在的檔案，不會跟著「連到其他位置的檔案或資料夾入口」繼續往外掃。這類入口通常稱為 symbolic link。一般整理手機照片備份時，通常不需要開這個選項。

如果你的備份資料夾裡有這類入口，而且你確定也要掃描它連到的內容，可以加上 `--follow-symlinks`：

```bash
python dedup_backup.py scan \
  --source /data/archive \
  --backup /data/old-backup \
  --out /tmp/duplicates.csv \
  --follow-symlinks
```

### 跳過刪除前驗證

`purge` 預設會在刪除前重新檢查檔案大小與 digest。若你確定 CSV 產生後檔案沒有變動，可以跳過驗證：

```bash
python dedup_backup.py purge \
  --backup /data/old-backup \
  --csv /tmp/duplicates.csv \
  --no-verify-hash \
  --yes
```

不確定檔案狀態時，不建議使用這個選項。
