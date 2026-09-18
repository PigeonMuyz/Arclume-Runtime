# 内置窗口类与加载锁回归验证

生产补丁同时修改 user32 回调和 win32u 的私有调用，必须配套构建 32 / 64 位 Windows 模块。macOS 宿主仍为 x86_64，不是 ARM64 通用二进制。

```sh
fixture_dir=$(mktemp -d /tmp/arclume-lock-fixtures.XXXXXX)
i686-w64-mingw32-gcc -Wall -Wextra -Werror -O2 tests/builtin-loader-lock.c -o "$fixture_dir/builtin-loader-lock32.exe" -luser32
x86_64-w64-mingw32-gcc -Wall -Wextra -Werror -O2 tests/builtin-loader-lock.c -o "$fixture_dir/builtin-loader-lock64.exe" -luser32
bash script/test-builtin-loader-lock.sh /absolute/path/to/extracted/arclume-wine-runtime-x86_64 "$fixture_dir"
```

脚本使用独立临时 Prefix，要求两种位数均输出 `LOCKTEST PASS`，并且只终止该测试 Prefix 的 wineserver。失败日志保留在脚本输出的临时目录；不读取、替换或删除用户容器。

该用例复现内置窗口类初始化与 loader lock 的锁顺序，不覆盖完整 YY 频道生命周期。YY 在麦序模式下可能仍出现交互无响应。
