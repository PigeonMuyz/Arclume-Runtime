# 内置窗口类与加载锁实验

用户实测更新：本轮 YY 进入频道仍然白屏并卡住。并发夹具通过并不等于 YY 已修复；本补丁继续保持实验状态，需对新现场重新取证。

## 范围与结论

针对 Wine 11 / CrossOver 26.3 的初始化死锁，不是已确认的 YY 绘制修复。
旧路径：线程 A 持有 `pthread_once` 初始化保护，加载内置光标时等待 loader lock；线程 B 在 DllMain 中持有 loader lock，注册窗口类又等待同一个初始化保护。

补丁让 user32 首先取得可重入的 loader lock，再执行一次性内置类初始化。窗口类注册仍在 win32u 完成，默认布局和主题加载仍保留。异常退出通过 finally 释放加载锁。
主题加载可能重入 user32，因此在窗口类和布局就绪后标记初始化完成；没有跳过类注册、清除用户配置或修改 YY 文件。

**实验私有接口成组部署**：两种 PE 架构的 user32.dll 和 Unix win32u.so 必须匹配。新 CallNoParam 编号仅追加，无需改变 WOW64 原有透传或 callback table 编号。此改动影响同一进程所有内置窗口类，尚不满足通用发布要求。

## 可重复夹具

```sh
i686-w64-mingw32-gcc -Wall -Wextra -Werror -O2 tests/builtin-loader-lock.c -o "$fixtures/builtin-loader-lock32.exe" -luser32
x86_64-w64-mingw32-gcc -Wall -Wextra -Werror -O2 tests/builtin-loader-lock.c -o "$fixtures/builtin-loader-lock64.exe" -luser32
bash script/test-builtin-loader-lock.sh "$runtime" "$fixtures"
```

`fixtures` 必须是已经创建的输出目录，`runtime` 是完整独立 Runtime。脚本自行新建临时前缀，不接受真实用户前缀，并在完成或超时后终止该临时前缀的 wineserver。保留日志和临时前缀供诊断，不删除用户数据。

夹具只修改自身的 KernelCallbackTable，按本项目 Wine 11 私有 ABI 在第一个内置光标加载回调暂停工作线程，强制制造现场的交错顺序。不能拿它对任意 Windows/Wine 版本或真实 YY 进程做注入。该回调未触发则返回 SKIP/失败，不冒充通过。

对照预期：旧版输出 `holds loader lock: no` 后无法完成注册；候选输出 `yes`，随后注册和内置 Button 创建都成功。仅有退出码 0 不代表成功：Wine 被 wineserver 终止也可能返回 0，必须检查 PASS 标记和超时标记。

首次仅使用线程延迟的夹具在旧版也通过，未能重现；最终夹具已改成上述回调门控。没有把那次结果计为修复证明。

## 本次构建和证据（2026-09-09）

- 源码：当前锁定的 Wine 11.0 + FineWine e5d4ccad，构建时应用 `patches/experimental/0001-builtin-class-loader-lock.patch`。
- 新构建目录：`work/build/yy-lock-test.qx1pJF`。使用 x86_64 宿主编译器、`MACOSX_DEPLOYMENT_TARGET=10.15`、`ac_cv_func_pipe2=no`、兼容 x86_64 freetype 库，配置 `--enable-archs=i386,x86_64 --disable-tests --prefix=/`。
- 编译目标：`make -j8 dlls/user32/i386-windows/user32.dll dlls/user32/x86_64-windows/user32.dll dlls/win32u/win32u.so`；三者均成功。
- 基底：已核验的 `arclume-wine-1.1.1-x86_64.tar.xz`，SHA-256 `aaea92debee5611c03683e7f1fefb4608a4ed609b27a4d24d5939a2fcf19d903`。基底解包到新目录，仅替换上述三个组件，win32u.so 做本地 ad hoc 签名并验证。
- 候选：`work/build/yy-patched-runtime.Ql5tuS/arclume-wine-runtime-x86_64`，标记 `.arclume-yy-lock-test`；正式 Runtime、源码版本字段、manifest 均未改。
- 注意：仓库发布字段仍为 1.1.0，基底为 1.1.1；这是混合来源的受控三组件实验，不是可发布的 1.1.1 重建，未确认包含这些组件的所有已发布构建差异。其余组件保持基底 1.1.1。
- 最终基线日志：`/tmp/arclume-builtin-lock-test.etaAEh`。32 位由脚本 15 秒终止；64 位另行在同一临时前缀运行并由 20 秒 watchdog 终止，均无 PASS。
- 候选日志：`/tmp/arclume-builtin-lock-test.2Og4IA`，32/64 位均显示加载锁已持有且 PASS。
- 构建日志：`/tmp/arclume-yy-lock-configure.log`、`/tmp/arclume-yy-lock-build.log`。Runtime preflight 通过，日志 `/tmp/arclume-yy-lock-runtime-preflight.log`。

补丁保存在 `experimental/`，不会被常规源码同步自动应用。实验组件构建后，将共享 `work/wine` 中本次改动还原到试验前的内容；候选二进制和补丁均保留。再次构建实验版需显式应用补丁并使用双架构配置。普通 `build-runtime.sh` 的默认单架构配置不能用于这个实验补丁的配套部署。

## YY 实测与撤回

Arclume 的诊断脚本仅在显式设置 `ARCLUME_YY_TEST_RUNTIME` 且候选带专用标记时选择该 Runtime。此次保留前轮 `--run-osr-cpu` 参数及已核验的 DNS 内存补丁、绿色适配，只更换 Runtime。关闭先前全部 YY/Wine 测试进程后才启动，避免同一前缀混跑 wineserver。

YY 频道显示、按钮响应、语音收发、反复进出频道和不附加调试器的启动仍需逐项确认。不要因并发夹具通过就写入正式 Adapter 或发布 Runtime。退出独立实验后，不设置覆盖变量走原启动入口即可；不需要删除/恢复用户前缀。
