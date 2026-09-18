# Wine Dock 图标留白

- 在 macdrv 输出 NSApplication 图标前计算可见边界；超出画布 80% 的主体等比例缩小，保留透明轮廓，不修改应用自身图标资源。
- 已有足够留白的图标不再次缩小，空图和无图保持回退行为；同时覆盖 CGImage 数组与图标 URL 的入口。
- Runtime 1.1.2，runtimeABI / prefixABI 不变。另包含独立记录的 YY 加载锁补丁；不宣称修复所有频道长时间卡住问题。
- 回滚为此前验证过的 1.1.1 Runtime；不删除或恢复用户 Prefix。
- 验证：`tests/dock-icon.m` 使用生产图标函数，覆盖空图、透明图、方形、横图、竖图和已有留白。
