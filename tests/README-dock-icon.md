# Dock 图标留白验证

在已同步的 Wine 源码上直接编译生产实现，不启动 Wine，也不访问用户 Prefix：

```sh
test_dir=$(mktemp -d /tmp/arclume-dock-test.XXXXXX)
clang -Wall -Wextra -Werror -Wno-unused-parameter -framework AppKit \
  -I work/build/wine-wow64/include -I work/wine/dlls/winemac.drv \
  tests/dock-icon.m work/wine/dlls/winemac.drv/cocoa_icon_utils.m \
  -o "$test_dir/dock-icon-test"
"$test_dir/dock-icon-test"
```

验证空输入、全透明、方图、横图、竖图、已有留白；可见边界以 alpha > 24 测量。
宽高比不变，不放大已有留白图像，不裁切资源。输出 512px 透明画布。
真实 Dock 需要重新启动对应 Wine 应用观察；算法通过不代表 YY 频道卡住已解决。
