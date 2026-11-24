# 邮件 DSH 插件

独立安装包为 `@alcor/mail`，适配官方 DSH Desktop 0.2.2-rc.5，支持 Windows x64 和 Apple 芯片的 Mac。在 DSH 的插件设置添加 IMAP 邮箱、设置授权码和文件夹，并按邮箱开启或停用对话读取。

凭据仅由 DSH 凭据服务管理，连接设置只供本机账号使用。模型工具通过 DSH 工具权限启用或限制。启用 Alcor 时可在简报中使用同一已配置来源，现有配置和已选范围沿用原来的连接身份。

从本仓的 Release 下载 `alcor-mail-0.2.0.tgz`，运行 `dsh plugin --profile desktop add /path/to/alcor-mail-0.2.0.tgz`，然后在插件页启用。旧版本使用同一包名，可原地升级。

独立 MCP 服务的用法见本仓根 README。构建插件时将 Alcor 产品仓克隆到相邻的 `Alcor/` 目录，或将 `ALCOR_SOURCE` 指向 Alcor 检出目录。使用 Python 3.12 的 Conda 环境或本仓 `.venv`，从本仓根目录运行：

```text
python -m pip install --require-hashes -r requirements.lock
python -m pip install PyInstaller==6.22.3
cd plugin
npm ci
npm pack
```

安装包自带当前构建平台的 MCP 服务。下载 CI 产物时选择对应的 `win-x64` 或 `mac-arm64`。
