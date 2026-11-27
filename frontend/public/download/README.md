# download

站点「成就档案 → 绑定 → 本机助手」的下载目录。

这里的 `ArknightsAchvAgent.exe` **不进仓库**，由源码现场构建：

```powershell
pwsh -File scripts\build-agent.ps1
```

- 源码：`agent/achv_agent.py`
- 构建脚本：`scripts/build-agent.ps1`
- PyInstaller spec：`agent/ArknightsAchvAgent.spec`
