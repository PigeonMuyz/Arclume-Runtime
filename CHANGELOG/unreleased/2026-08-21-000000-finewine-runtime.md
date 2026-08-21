# FineWine Runtime patch integration

- 将 `stoicswe/Endfield_FineWine` 的 23 个 Wine 补丁以锁定修订、固定顺序和 SHA-256 清单纳入 Runtime；已在 CrossOver 26.3.0 / Wine 11.0 源码上验证可完整应用。
- 将 Arclume Wine 升级为 `1.1.0`，维持 Runtime ABI 与 Games 容器 ABI。
- 新增 Runtime 的 GitHub PR 前置审核以及基于 `release:` 指令的构建、校验和发布工作流。
- 发布工作流增加 `pre-release:` 通道：Pre-Release 使用独立 tag 与 manifest channel，并在成功发布后仅保留最新一个 Arclume Wine Pre-Release。
- 修复以同名 Runtime archive 作为重打包基线时的目录自移动错误，使通道化 manifest 可复用现有 Runtime。
