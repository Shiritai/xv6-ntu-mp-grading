# xv6-ntu-mp 助教作業發布與自動化評分完整指南

本指南專為助教 (TA) 設計，詳細解說從作業發布、學生輔導、到期末全自動無痛評分 (Zero-Submission 零繳交模型) 的完整生命週期與操作指令。

## 1. 儲存庫權責劃分

我們採用了 Dual-Repo 架構，隔離「學生可見內容」與「助教評分用內容」：

### 📌 `xv6-ntu-mp` (公開模板庫) -> [Shiritai/xv6-ntu-mp](https://github.com/Shiritai/xv6-ntu-mp)

此 Repo 為學生作業的出發點。學生需在作業公佈時 Fork 或 Use Template (後者支援 Private repo)。

* **`doc/`**: 放完整的規格文件 (Markdown 格式)。
* **`kernel/`, `user/`**: 放系統核心與學生需實作的模板程式碼 (Skeleton)。
* **`tests/`**: 只放 **公開測資 (Public Tests)** (`test_mpX_public.py`)，讓學生在本地與自己的 GitHub CI 上能隨時看到基礎分數。
* **`mp.sh` & `.github/workflows/grading.yml`**: CI/CD 自動化評分引擎入口與 GitHub Actions 設定。

### 📌 `xv6-ntu-mp-grading` (助教評分庫)

此 Repo 用於管理學生白名單、自動化腳本及各次作業的隱藏依賴。

* **`tools/`**: 放置通用的全自動化評分組合腳本集，包含接受邀請、打成績、擷取成績等。
* **`mpX/`**: 放置各次作業專屬的私有解答與測資酬載 (Payload)，例如 `mp0/`。

## 2. 作業發布與 Payload 準備 (以 MPX 為例)

當您要發佈一份新作業 (例如 `mpX`) 給學生寫之前，在 `xv6-ntu-mp-grading` 庫中您必須建立以下兩個核心目錄。為了防止私測外流，預設的 `.gitignore` 會隱藏真實的 `mp0/`、`mp1/` 等作業資源檔案，您可以參考 `mp-example/` 來了解所需的檔案結構：

### A. 準備官方解答 (`mpX/local_answer/`)

包含作業的參考解答（如 `mpX.c`）。這主要是給助教團隊內部驗證腳本與測資是否能拿到滿分。**這不會分發給學生**，甚至可以完全省略。

### B. 準備公開同步資產 (`mpX/public/`) [重要：Hot-Sync]

📌 **此目錄用於「作業期間」的熱同步更新。**
包含隨時需要分發給學生的內容（如：修正後的規格文件 `doc/`、新增的公開測資 `tests/`）。

* **觸發工具**：使用 `tools/broadcast_update.sh` 將此處內容平行推送至學生的私人儲存庫。
* **同步機制**：學生端執行 `mp.sh sync` 時，會自動無縫合併助教的最新 Commit。
* **注意**：請確保此處**不含任何私密資訊**。

### C. 準備評分 payload 與私密測資 (`mpX/payload/`) [重要：Zero-Submission]

📌 **此目錄用於「死線後」的一鍵自動評定，嚴禁於作業期間公開。**
零繳交評分模式的核心在於：死線一到，各評分工具會**強制覆蓋學生的儲存庫**，將 `payload/` 下的內容原封不動地推送過去。這確保了：

1. 學生無法竄改 CI 執行過程。
2. 私密測資與官方評分配置 (`mp.conf`, `grading.conf`) 在評分結束前絕對保密。

其檔案結構範例：

```text
xv6-ntu-mp-grading/mpX/payload/
├── .github/workflows/grading.yml   # 強制重置 Action 結構
├── mp.sh                           # 強制重置入口點
├── mp.conf                         # 強制重置評分環境 (如信任網址)
├── tests/grading.conf              # 官方測資權重配置
└── tests/test_mpX_private.py       # 私密測試測資
```

> **⚠️ 助教注意**：每次發布新作業，請確保 `payload/` 內的 `.yml`, `sh`, `conf`, `grading.conf` 皆與 `xv6-ntu-mp` 的最新期望配置同步。

---

## 3. 助教自動評分結算 SOP

學生在作業期間的流程非常簡單：不用填表單，不用上傳 COOL，只需寫程式並 Push 到自己的 Private Repo (並且已將本作業助教的 GitHub 帳號加入 Collaborator)。
當作業死線 (Deadline) 屆至，助教請按照以下 **3 個步驟** 完成所有人的評分結算。

### Step 1: 準備學生白名單

> 🛑 **非常重要的規定**：所有學生的儲存庫**必須設為 Private**。評分工具內建了防禦機制：`accept_invite.sh` 會直接拒絕來自 Public Repo 的邀請（並印出警告清單），且 `grading_crawler.py` 會在抓取成績時主動即時檢查 Repository 的可見度。只要抓到是 Public，無論 Action 執行結果為何，該名學生的最終成績都會被無條件**覆寫為 0 分**。

請從貴校的學習管理系統 (LMS，如 Canvas, Moodle, NTU COOL) 或報名表單 (如 Google Forms) 匯出學生提交的 **GitHub Username**。將這些帳號取出來，每一行一個帳號，存放到純文字白名單檔案 `whitelist.txt` 中。

如果您使用的是 **Google 表單試算表**，且 GitHub 帳號位於第 3 欄，您可以透過以下指令全自動完成下載與白名單的萃取：

```bash
cd xv6-ntu-mp-grading/tools

# 設定您的 Google Sheet 參數
SHEET_ID="..."
SHEET_GID="..."

# 1. 下載為 TSV 格式，去除標題行 (tail -n +2)，保留特定欄位並轉為 CSV：
curl -s -L "https://docs.google.com/spreadsheets/d/$SHEET_ID/export?format=tsv&gid=$SHEET_GID" | \
tr -d '\r' | tail -n +2 | cut -f3,4,5 | \
awk -F'\t' '{for(i=1;i<=NF;i++) printf "\"%s\"%s", $i, (i==NF?ORS:",")}' > student-github-accounts.csv

# 2. 爬取第 3 欄位 (GitHub 帳號)，去除雙引號，並輸出至 whitelist.txt：
awk -F'","' '{print $3}' student-github-accounts.csv | sed 's/"//g' > ../whitelist.txt
```

* 📂 **產出路徑**: `xv6-ntu-mp-grading/whitelist.txt`
* 📝 **內容範例**:

  ```text
  b12345678-test
  os-genius
  anon-chihaya
  ```

### Step 2: 批次接受邀請與清點名單

學生創建 Private Repo 後會發送邀請給助教帳號。我們不需要點開信箱一封封按接受，請用以下指令：

```bash
cd xv6-ntu-mp-grading/tools
# 登入具有權限的助教 GitHub 帳號 (只需執行一次)
gh auth login

# 手動或自動創建 whitelist.txt

# 執行自動接受腳本，產出放在對應的作業目錄下
./accept_invite.sh -f ../whitelist.txt -r "ntuos2026-mpX" -o ../mpX/result/students_mpX.json
```

**做什麼事？**

1. **階段一 (接受邀請)**：腳本首先呼叫 GitHub API 列出所有待決的 Repository 邀請，核對 `whitelist.txt` 與 `"ntuos2026-mpX"` 字串後，自動批次接受邀請。**最重要的是，它會跳過任何來自 Public 儲存庫的邀請，並對助教發出警告，以便及時通知學生修正可見度。**
2. **階段二 (全局掃描與防呆)**：無論上述是否有新邀請，腳本都會強制爬取當前助教帳號名下「所有具備 Collaborator 權限的 Repository」。它會利用 Github 官方的回傳狀態，實時與 `whitelist.txt` 進行交集比對。
3. **安全匯出**：最終，將這份 100% 準確的實際清單 (例如 `anon-chihaya/ntuos2026-mpX`) 覆寫登錄至 `../mpX/result/students_mpX.json` 中，作為下一步的資產。

> 💡 **提示**：由於階段二是直接向 GitHub 索要當前的「確定已連線狀態」，這使得此腳本執行中斷一百次，只要帳號權限還在，重跑腳本永遠能完美建構出 100% 沒有遺漏的 `students_mpX.json` 名單！

### Step 3: 一鍵自動化評分與結算

**這是一鍵到底的指令**。確認所有的 Repo 皆已登錄於 `../mpX/result/students_mpX.json` 之後，即可發動評分引擎：

```bash
cd xv6-ntu-mp-grading/tools
./auto_grade_mp.sh --mp mpX --students ../mpX/result/students_mpX.json
```

*(提示：由於批改時 CI 執行通常需要耗時 5-10 分鐘，如果還沒全部跑完，腳本會提示正在執行中的同學清單，並且輸出部份成績單。如果同學的程式碼完全沒變更，且 Payload 也沒更新，系統預設會**跳過觸發 (避免浪費 CI 資源)**，直接去抓上一次的成績；若您想強制所有人重新跑一次 CI，請加上 `--force` 參數。)*

**做什麼事？**
這是一支將 `trigger_grading` 與 `grading_crawler` 無縫串接的平行化腳本：

1. **平行注入 Payload**: 透過多執行緒遍歷名單裡的每一位學生，用指令將 `mpX/payload/` 的內容直接覆蓋寫入學生的 Repo 根目錄，並以助教您的身份並行 Push 提交上去。這將直接覆蓋學生的 CI 設定並且強迫套用最新版本的 Sanitizer。由於 Payload 移除了「偵測助教 Commit 即跳過」的邏輯，正式評分可以順利進行。
2. **平行觸發 CI**: 由於是正式的 Commit Push，學生的 GitHub Actions 會被喚醒並執行官方的編譯與測資 (包含我們剛放進去的 Private Tests)。而這筆 Commit 的 SHA 將被儲存為唯一的防偽指紋。
3. **無狀態單筆爬取與備份**: 腳本隨即呼叫爬蟲提取當下瞬間的即時成績快照。當它發現該指紋的 Action 已亮綠燈 (跑完) 後，它會解壓縮 `.zip` 下載純淨的 `report.json`。最重要的，**每一個同學的 `report.json` 原始成績單都會被獨立保存在 `../mpX/result/reports/` 檔案夾內，供日後審計查核**。未跑完的同學會被標示在名單上，您只需稍後再執行一次腳本即可無縫補齊。
4. **輸出報表**: 最終，為您在 `mpX/result/` 目錄產出 `final_grades.csv` 與 `.json` 檔案。

```csv
Repository,Status,Final Score,Run URL
anon-chihaya/ntuos2026-mpX,Success,100,https://github.com/anon-chihaya/ntuos2026-mpX/actions/runs/223...
```

**結算產物：**

* `../mpX/result/final_grades.csv`: 可直接開啟或上傳到 NTU COOL 轉換登錄。
* `../mpX/result/reports/`: 內含全班個別的詳細執行日誌與 `report.json`。

您現在可以直接將 `final_grades.csv` 開啟或上傳到 NTU COOL 轉換登錄了！

---

## 附錄：評分工具 API 參考指南

`tools/` 核心工具集封裝了整個零繳交自動評分引擎。這些腳本高度解耦、具備冪等性 (Idempotency)，旨在應對各種中斷與環境異常，確保評分過程的絕對穩定。

### `accept_invite.sh`

負責儲存庫發現與盤點的 Bash 腳本。

* **運作機制**：採用雙軌掃描策略。首先，透過 GitHub API `user/repository_invitations` 批次接受所有待決的 Collaborator 邀請。接著，透過 `user/repos?affiliation=collaborator` 爬取當前助教具備權限的所有儲存庫，並與白名單及特定的關鍵字進行嚴格的交集比對。
* **冪等性**：執行過程無狀態 (Stateless)，完全依賴 GitHub 伺服器回傳的真實授權狀態。多次重複執行此腳本，永遠能完美重建同一份無遺漏、無重複的學生清單 (JSON)。
* **用法**：`./accept_invite.sh -f <whitelist_txt> -r <repo_keyword> -o <output_json> [-d]`
  * `-f`：白名單檔案路徑 (每行一個 GitHub Username)。
  * `-r`：目標 Repo 必須包含的關鍵字 (例如 `ntuos2026-mpX`)。
  * `-o`：輸出目標 JSON 檔案的位置 (例如 `students_mpX.json`)。
*   **運作機制**：採用雙軌掃描策略。首先，透過 GitHub API `user/repository_invitations` 批次接受所有待決的 Collaborator 邀請。接著，透過 `user/repos?affiliation=collaborator` 爬取當前助教具備權限的所有儲存庫，並與白名單及特定的關鍵字進行嚴格的交集比對。
*   **冪等性**：執行過程無狀態 (Stateless)，完全依賴 GitHub 伺服器回傳的真實授權狀態。多次重複執行此腳本，永遠能完美重建同一份無遺漏、無重複的學生清單 (JSON)。
*   **用法**：`./accept_invite.sh -f <whitelist_txt> -r <repo_keyword> -o <output_json> [-d]`
    *   `-f`：白名單檔案路徑 (每行一個 GitHub Username)。
    *   `-r`：目標 Repo 必須包含的關鍵字 (例如 `ntuos2026-mpX`)。
    *   `-o`：輸出目標 JSON 檔案的位置 (例如 `students_mpX.json`)。
    *   `-d`：Dry-run 模式。僅預覽比對邏輯與即將呼叫的 API，但不實際執行 PATCH 接受邀請。

### `auto_grade_mp.sh`

身兼最高指揮官的 Bash 腳本，負責統籌整個自動評分生命週期。

*   **運作機制**：首先派發 `trigger_grading.py` 將測資覆蓋並點燃 CI。隨後它會無狀態地自動呼叫單次 `grading_crawler.py` 進行非阻塞快照擷取，並向您彙報還沒完成的同學進度。
*   **用法**：`./auto_grade_mp.sh --mp <mp_id> [--students <roster_json> | --repo <owner/repo>] [--prefix <course_prefix>] [--force]`

### `trigger_grading.py`

由 Python 撰寫的多執行緒注入引擎，負責發放考題與觸發 CI。

* **冪等性與快取**：在執行 Commit 前，會先比對欲覆蓋的 Payload 檔案與學生 Repo 目前最新的 Tree 結構是否完全一致。如果完全相同，代表 Payload 沒有更新且學生並未竄改環境，系統將智慧略過該次 Commit。這能省下大量不必要的 GitHub Action 運算時間。可選用 `--force` 參數強制跳過比對執行覆蓋。

### `grading_crawler.py`

強健的 Python 異步爬蟲，負責監聽 CI 結果與解析 Artifacts。

* **運作機制**：利用 Git SHA 不可偽造的特性。對於 `trigger_grading.py` 發動的那筆特定 Commit SHA，爬蟲會針對每個學生尋找對應的 Workflow Run，並智慧輪詢等待狀態從 `in_progress` 轉為 `completed`。完成後，將下載測試所產出的 Artifact，並精準抽取裡面的 `report.json` 分析成績。
* **防作弊 (可見度檢查)**：在承認任何分數之前，它會對 Repository 發起即時的 API 查詢。如果此時庫被設為 `Public` (例如學生在發送 Action 成功後才改為公開)，爬蟲將毫不留情地祭出 `0` 分懲罰，並標註狀態為 `Public Repo Penalty`。
* **容錯性**：具備指數退避 (Exponential Backoff) 重試機制。能妥善處理各類異常狀況（例如編譯失敗或 Artifact 遺失），這些狀況會被安全地記錄為零分並輸出在成績報表中，絕不會導致腳本崩潰中斷。

### `broadcast_update.sh`

助教端「Hot-Sync」推播工具。

* **運作機制**：此腳本專門處理**作業期間**的公開資產同步。它會利用 `concurrent.futures` 模組，以多執行緒平行方式逐一 Clone 學生的私人 Repo，將 `mpX/public/` 的更新疊加其上並安全 Push 提交。這能完美迴避 Non-Fast-Forward 衝突，讓學生能一鍵 (`mp.sh sync`) 無痛合併最新的規格或測資修正。
* **安全性限制**：嚴禁存放任何私密測資於 `public/`。若要發布影響評分的正式內容（如 `grading.conf`），應優先放在 `payload/` 區。
* **用法**：`./broadcast_update.sh --mp <mp_id> --message <commit_message> [--repos-list <json_file>] [--workers <int>] [--dry-run]`
  * `--mp`：作業代號 (如 `mp0`)。資產應位於 `mpX/public/`。
  * `--message`：提交訊息，學生將在 git log 中看到此訊息。
  * `--repos-list`：目標學生 Repository 的 JSON 清單檔案（由 `accept_invite.sh` 產生）。
  * `--workers`：(選填) 平行處理的執行緒數量，預設為 4。
  * `--repo`：(選填) 指定單一目標庫 URL，主要用於測試。與 `--repos-list` 互斥。
  * `--dry-run`：預覽模式。僅在本地獨立的 `tmp/` 暫存目錄中執行同步與提交，不推送至遠端。
