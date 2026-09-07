# macOS 中文输入法与剪贴板修复

- Arclume Wine 升级至 `1.1.1`；Runtime ABI 与 Games 容器 ABI 保持不变。
- 用户主动粘贴时会在 50 毫秒内同步 macOS 剪贴板；后台轮询仍维持 2 秒。
- 为 macOS 输入法的别名键盘布局传递实际语言区域及对应代码页，使简体中文输入法向 Windows 应用发送正确的输入语言变更。
- 不改变 EditMenu=key 的标准键盘输入模式。
