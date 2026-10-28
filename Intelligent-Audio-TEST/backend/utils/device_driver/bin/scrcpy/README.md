# bin/scrcpy —— 内置 scrcpy（音频抓取用）

`android_scrcpy_audio.py` 用 scrcpy 4.1 的纯音频模式抓 Android 设备的
`playback` / `mic` 两路音频。运行 scrcpy **只需要下列 9 个文件**（adb 不在此列，
用系统 PATH 里的 adb 即可；已实测从任意目录直接运行 OK）：

```
scrcpy.exe
scrcpy-server          # 会被 push 到设备
SDL3.dll
avcodec-62.dll
avformat-62.dll
avutil-60.dll
swresample-6.dll
libusb-1.0.dll
LICENSE.txt
```

## 为什么这些文件不在 git 里

二进制合计约 **16.75 MB**（其中 `scrcpy.exe` + DLL 就 16.7MB），且是第三方发布物、
会随 scrcpy 版本整体替换。入库会永久污染 git 历史且难以清理，因此仓库只保留本说明和
`vendor_scrcpy.ps1`，二进制按需拷入。`.gitignore` 已忽略本目录下的 `*.exe` / `*.dll` /
`scrcpy-server`（本 README 与脚本仍受版本管理）。

## 一键拷入（在仓库根目录执行一次）

```powershell
# 本机便携版来源
powershell -ExecutionPolicy Bypass -File `
  Intelligent-Audio-TEST\backend\utils\device_driver\bin\scrcpy\vendor_scrcpy.ps1
```

拷完执行 `...\bin\scrcpy\scrcpy.exe --version` 能看到 `scrcpy 4.1` 即成功。

## 路径解析顺序（`resolve_scrcpy_path()`）

1. 环境变量 `SCRCPY_PATH`（exe 或目录都行）；
2. 本目录的 `scrcpy.exe`（内置目录）；
3. 系统 `PATH` 里的 `scrcpy`；
4. 开发机兜底 `D:\work\_android\scrcpy-win64-*\scrcpy.exe`。

所以即使忘了拷，本机仍能跑（走第 4 条），只是换机器/进 CI 会失效。
