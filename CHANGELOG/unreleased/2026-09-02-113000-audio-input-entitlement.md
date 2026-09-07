# Wine CoreAudio 签名能力

- 当构建时提供 `RUNTIME_CODESIGN_IDENTITY`，为实际承载 Windows 游戏的 Wine loader 写入 macOS 音频输入 entitlement。
- 保持其余运行时 Mach-O 的最小签名；此改动不修改 Runtime ABI、Games 容器 ABI 或用户前缀内容。
- Runtime Release workflow 会在构建后验证该 entitlement；未配置证书时拒绝发布，避免将无麦克风能力的 Runtime 覆盖给用户。
