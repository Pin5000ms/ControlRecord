# 開發與擴充

## 本機開發

使用 Python 3.10 x64。本次執行環境為 3.10.10。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`requirements.txt` 固定直接相依版本；`requirements-lock.txt` 記錄本次完整執行相依版本。測試使用標準函式庫 unittest。

若本機套件快取完整，可執行 `tools/restore_cached_wheels.py` 將所需 wheel 複製至專案內的 `artifacts/wheels` 後離線安裝。此腳本不修改來源快取。

## 模組邊界

| 模組 | 責任 |
|---|---|
| `model.py` | 帶版本的 Script / Event、事件驗證、JSON 原子寫入 |
| `capture.py` | 滑鼠事件擷取、全域控制快捷鍵；不記錄一般鍵盤輸入 |
| `playback.py` | 與裝置無關的時間排程、循環、取消與清理 |
| `windows.py` | DPI、SendInput、螢幕環境、防休眠、單一執行個體 |
| `video.py` | FFmpeg 子程序生命週期、錄影就緒、進度監控與 MP4 封裝 |
| `worker.py` | 執行任務、錄影／重播協調、錯誤處理與結果保存 |
| `storage.py` | 腳本列表、匯入、設定、歷史紀錄 |
| `ui.py` | Qt 主視窗與介面狀態 |

介面在 Qt 主執行緒。錄製 listener 只寫入記憶體事件，不做磁碟存取。重播與錄影管理在 QThread，影片編碼在 FFmpeg 子程序。F12 的 hook 先設置 `threading.Event`，才向介面發送訊號，因此不依賴介面刷新速度取消重播。

程式狀態為 `idle → prepare_record → recording → idle` 或 `idle → countdown → running → stopping → idle`。錄製與重播互斥。關閉視窗時若有執行任務，先取消並等待影片保存，再關閉程式。

## 腳本格式與鍵盤擴充

腳本是資料，不會執行匯入檔案內的 Python 或 shell 指令。每個事件具有 `t`（相對於錄製起點的秒數）、`kind`（具裝置命名空間的事件類型）、`data`。`duration` 獨立於最後一個事件時間，以保存結尾等待。

目前類型：`mouse.move`、`mouse.down`、`mouse.up`、`mouse.scroll`。檔頭含 `schema_version: 1`、ID、名稱、建立時間、螢幕資訊。

未來加入鍵盤的建議步驟：

1. 加入鍵盤擷取 adapter，讓滑鼠與鍵盤共用錄製起點與事件接收器，合併成有序事件串列。可將目前 MouseRecorder 的事件緩衝抽成 CaptureSession。
2. 定義 `keyboard.down` / `keyboard.up`，例如保存 `scan_code`、`extended` 和需要時的 `virtual_key`，不要只儲存目前鍵盤配置的顯示字元。
3. 透過 `EventRegistry.register()` 加入新資料驗證器；將預設 registry 工廠擴充為完整事件集合。所有 JSON 載入仍經由同一組驗證。
4. 透過 `WindowsInput.register_handler()` 加入鍵盤 SendInput 處理器。`KEYBDINPUT` 已預留。維護工具注入的按鍵狀態，於停止、異常及每輪結束釋放。
5. 增加按鍵平衡檢查、組合鍵、鍵盤配置與控制快捷鍵排除測試。F8/F12 的控制行為優先，不應錄入腳本。

重播排程和循環邏輯不需因新增鍵盤而改寫。`test_future_adapter_can_register_without_scheduler_changes` 驗證已能註冊鍵盤事件並經由相同排程執行。第一版對尚未註冊的事件明確拒絕，避免靜默漏掉動作。

日後圖片辨識可使用相同命名空間設計，例如 `vision.wait` / `vision.click`；這類動作具有不定長等待，需另外定義與原始時間軸混用時的排程規則。

## 打包

本次網路無法連線至套件下載站，使用本機 CPython 與 Windows 內建 .NET Framework C# 編譯器打包，無需 PyInstaller。

```powershell
.\.venv\Scripts\python.exe tools\make_icon.py
.\.venv\Scripts\python.exe tools\build_portable.py
```

亦可執行 `build.cmd`（會先執行測試）。輸出至 `dist/ControlRecord`；若目錄已存在，建立帶時間的新目錄，不刪除既有版本或資料。

EXE 是小型 Windows 啟動器，負責呼叫隨附的 `runtime/pythonw.exe app/main.py` 並傳遞參數。所有產品邏輯仍在 Python。`python310._pth` 限定執行時的模組路徑，啟動不依賴開發機的 Python 安裝位置、PATH 或虛擬環境。

修改 Python 檔案後需重新打包，原始碼與已打包的 `app` 副本不會自動同步。套件與 Python 授權文件一起保留在輸出目錄中。建置詳細資訊見 `build-info.json`。

