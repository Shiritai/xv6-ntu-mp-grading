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

* **`tools/`**: 放置通用的全自動化評分組合腳本集，包含接受邀請、發動評分、擷取成績等。
* **`mpX/`**: 放置各次作業專屬的私有解答與測資酬載 (Payload)，例如 `mp0/`。

## 2. 作業發布與 Payload 準備 (以 MPX 為例)

當您要發佈一份新作業 (例如 `mpX`) 給學生寫之前，在 `xv6-ntu-mp-grading` 庫中您必須建立以下兩個核心目錄。為了防止私測外流，預設的 `.gitignore` 會隱藏真實的 `mp0/`、`mp1/` 等作業資源檔案，您可以參考 `mp-example/` 來了解所需的檔案結構：

### A. 準備官方解答 (`mpX/local_answer/`)

存放該次作業的 Reference Solution (例如 `mpX.c`)，供助教團隊內部驗證腳本與測資是否通過滿分使用，**不參與自動化發放流程**，也可以不必放置。

### B. 準備評分資料與私有測資 (`mpX/payload/`)

📌 **這是最重要的資料夾**。
零繳交流程依賴於死線後，將 `payload/` 原封不動地**強制覆蓋蓋入學生的儲存庫**。這能確保：

1. 學生無法竄改 CI 的執行過程。
2. 測資到死線結束後才公開。

對於 `mpX`，您的 `payload/` 內必須包含：

```text
xv6-ntu-mp-grading/mpX/payload/
├── .github/workflows/grading.yml   # 強制重置 Action 結構，防止竄改並保證引入最新 Sanitizer
├── mp.sh                           # 強制重置 QEMU 與測試入口點
├── mp.conf                         # 強制重置評分環境變數與信任網址 (TRUSTED_REPO)
└── tests/test_mpX_private.py       # 私有測試測資
```

> **⚠️ 助教注意**：每次發布新作業，請確保 `payload/` 內的 `.yml`, `sh`, `conf` 皆與 `xv6-ntu-mp` 的 main 分支最新版同步。**注意 Payload 中的 `mp.sh` 應移除 `check_ta_commit` 邏輯，以確保由助教觸發的正式評分 CI 能順利執行。**

---

## 3. 助教自動評分結算 SOP

學生在作業期間的流程非常簡單：不用填表單，不用上傳 COOL，只需寫程式並 Push 到自己的 Private Repo (並且已將本課程助教的 GitHub 帳號加入 Collaborator)。
當作業死線 (Deadline) 屆至，助教請按照以下 **3 個步驟** 完成所有人的評分結算。

### Step 1: 準備學生白名單

> 🛑 **非常重要的規定**：所有學生的儲存庫**必須設為 Private**。評分工具內建了防禦機制：`accept_invite.sh` 會直接拒絕來自 Public Repo 的邀請（並印出警告清單），且 `grading_crawler.py` 會在抓取成績時主動即時檢查 Repository 的可見度。只要抓到是 Public，無論 Action 執行結果為何，該名學生的最終成績都會被無條件**覆寫為 0 分**。

請從貴校的學習管理系統 (LMS，如 Canvas, Moodle, NTU COOL) 或報名表單 (如 Google Forms) 匯出學生提交的 **GitHub Username**。將這些帳號取出來，每一行一個帳號，存放到純文字白名單檔案中。注意，此檔案可以任意命名且放置於任何目錄下，通常會放在專案根目錄或 `tools/` 資料夾內。

* 📂 **路徑範例**: `xv6-ntu-mp-grading/whitelist.txt`
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

# 執行自動接受腳本，產出放在對應的作業目錄下
./accept_invite.sh -f ../whitelist.txt -r "ntuos2026-mpX" -o ../mpX/result/students_mpX.json
```

**做什麼事？**

1. **階段一 (接受邀請)**：腳本首先呼叫 GitHub API 列出所有待決的 Repository 邀請，核對 `whitelist.txt` 與 `"ntuos2026-mpX"` 字串後，自動批次接受邀請。**最重要的是，它會跳過任何來自 Public 儲存庫的邀請，並對助教發出警告，以便及時通知學生修正可見度。**
2. **階段二 (全局掃描與防呆)**：無論上述是否有新邀請，腳本都會強制爬取當前助教帳號名下「所有具備 Collaborator 權限的 Repository」。它會利用 Github 官方的回傳狀態，實時與 `whitelist.txt` 進行交集比對。
3. **安全匯出**：最終，將這份 100% 準確的實際清單 (例如 `anon-chihaya/ntuos2026-mpX`) 覆寫登錄至 `../mpX/result/students_mpX.json` 中，作為下一步的資產。

> 💡 **提示**：由於階段二是直接向 GitHub 索要當前的「確定已連線狀態」，這使得此腳本執行中斷一百次，只要帳號權限還在，重跑腳本永遠能完美建構出 100% 沒有遺漏的 `students_mpX.json` 名單！

### Step 3: 一鍵自動化評分與結算

**這是一鍵到底的指令**。確認所有的 Repo 皆已登錄於 `../mpX/result/students_mpX.json` 之後，即可發動評分攻擊引擎：

```bash
cd xv6-ntu-mp-grading/tools
./auto_grade_mp.sh --mp mpX --students ../mpX/result/students_mpX.json
```

*(提示：如果您不想等 CI 跑完，只想先將測資推送上去，可以附加 `--no-wait` 參數，引擎會在丟出 Payload 後直接離開，您可以晚點再下同一道沒有 --no-wait 參數的指令來純抓取成績。另外，如果同學的程式碼完全沒變更，且 Payload 也沒更新，系統預設會**跳過觸發 (避免浪費 CI 資源)**，直接去抓上一次的成績；若您想強制所有人重新跑一次 CI，請加上 `--force` 參數。)*

**做什麼事？**
這是一支將 `trigger_grading` 與 `grading_crawler` 無縫串接的平行化腳本：

1. **平行注入 Payload**: 透過多執行緒遍歷名單裡的每一位學生，用指令將 `mpX/payload/` 的內容直接覆蓋寫入學生的 Repo 根目錄，並以助教您的身份並行 Push 提交上去。這將直接覆蓋學生的 CI 設定並且強迫套用最新版本的 Sanitizer。由於 Payload 移除了「偵測助教 Commit 即跳過」的邏輯，正式評分可以順利進行。
2. **平行觸發 CI**: 由於是正式的 Commit Push，學生的 GitHub Actions 會被喚醒並執行官方的編譯與測資 (包含我們剛放進去的 Private Tests)。而這筆 Commit 的 SHA 將被儲存為唯一的防偽指紋。
3. **輪詢爬取與備份**: 腳本隨即進入輪詢等待模式 (Polling)。當它發現該指紋的 Action 順利亮起綠燈 (跑完) 後，它會解壓縮 `.zip` 下載純淨的 `report.json`。最重要的，**每一個同學的 `report.json` 原始成績單都會被獨立保存在 `../mpX/result/reports/` 檔案夾內，防止污染專案根目錄，並供日後審計查核**。
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
  * `-d`：Dry-run 模式。僅預覽比對邏輯與即將呼叫的 API，但不實際執行 PATCH 接受邀請。

### `auto_grade_mp.sh`

身兼最高指揮官的 Bash 腳本，負責統籌整個自動評分生命週期。

* **運作機制**：首先派發 `trigger_grading.py` 將測資覆蓋並點燃 CI。若未指定 `--no-wait`，接著會自動呼叫 `grading_crawler.py` 進入輪詢狀態，等待並彙整 `.csv` 與 `.json` 成績單。
* **用法**：`./auto_grade_mp.sh --mp <mp_id> --students <roster_json> [--no-wait] [--force] [--max-attempts <int>] [--wait-interval <int>]`

### `trigger_grading.py`

由 Python 撰寫的多執行緒注入引擎，負責發放考題與觸發 CI。

* **運作機制**：透過 `concurrent.futures` 平行調用 `gh api`。將本地端的 `mpX/payload/` 檔案結構，原封不動地強制 Commit 到學生儲存庫的根目錄，藉此建構官方基準的測試環境並觸發 GitHub Actions。
* **冪等性與快取**：在執行 Commit 前，會先比對欲覆蓋的 Payload 檔案與學生 Repo 目前最新的 Tree 結構是否完全一致。如果完全相同，代表 Payload 沒有更新且學生並未竄改環境，系統將智慧略過該次 Commit。這能省下大量不必要的 GitHub Action 運算時間。可選用 `--force` 參數強制跳過比對執行覆蓋。

### `grading_crawler.py`

強健的 Python 異步爬蟲，負責監聽 CI 結果與解析 Artifacts。

* **運作機制**：利用 Git SHA 不可偽造的特性。對於 `trigger_grading.py` 發動的那筆特定 Commit SHA，爬蟲會針對每個學生尋找對應的 Workflow Run，並智慧輪詢等待狀態從 `in_progress` 轉為 `completed`。完成後，將下載測試所產出的 Artifact，並精準抽取裡面的 `report.json` 分析成績。
* **防作弊 (可見度檢查)**：在承認任何分數之前，它會對 Repository 發起即時的 API 查詢。如果此時庫被設為 `Public` (例如學生在發送 Action 成功後才改為公開)，爬蟲將毫不留情地祭出 `0` 分懲罰，並標註狀態為 `Public Repo Penalty`。
* **容錯性**：具備指數退避 (Exponential Backoff) 重試機制。能妥善處理各類異常狀況（例如編譯失敗或 Artifact 遺失），這些狀況會被安全地記錄為零分並輸出在成績報表中，絕不會導致腳本崩潰中斷。
