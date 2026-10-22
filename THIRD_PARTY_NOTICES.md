# 第三方元件

本地交付版本保留 Python 與相依套件原有授權文件。相依套件的 metadata 與 license 位於 `runtime/Lib/site-packages/*dist-info/`，Python 授權位於 `runtime/LICENSE.txt`。

- Python 3.10：Python Software Foundation，https://www.python.org/
- PySide6 Essentials / shiboken6 6.10.1：Qt for Python，https://doc.qt.io/qtforpython-6/
- pynput 1.8.1：https://github.com/moses-palmer/pynput
- six 1.17.0：https://github.com/benjaminp/six
- imageio-ffmpeg 0.6.0：https://github.com/imageio/imageio-ffmpeg
- 隨 imageio-ffmpeg 提供的 FFmpeg 7.1 執行檔：https://ffmpeg.org/ 。本次二進位檔的 `-L` 輸出標示 GNU GPL v3 或更新版本；相關建置及來源資訊見 https://github.com/imageio/imageio-binaries 。

本專案沒有修改上述套件的程式碼。打包器以檔案形式附帶 Python 模組、Qt 動態函式庫與獨立 FFmpeg 執行檔。若日後對外發佈，應隨所選二進位檔版本整理對應授權與來源提供事項。

