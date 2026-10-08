# 2026-09-27 多媒体候选验收

## 产物

- 候选：`1.1.3-dev.1`，本地临时签名，尚未发布或公证。
- 文件：`dist/arclume-wine-1.1.3-dev.1-x86_64.tar.xz`，155,675,564 字节（约 148.5 MiB）。
- SHA-256：`71f2b25c8b7752e30bfd387f0b168673b019a512039cf85d14c6852ddbecdda7`。
- GStreamer 1.28.7、FFmpeg 7.1.5、dav1d 1.5.3；宿主架构 x86_64，Wine Windows 模块保留 i386 / x86_64。
- Runtime ABI 1、Prefix ABI `arclume-jx3-prefix-1` 均未改变。

## 实际结果

| 检查 | 结果 |
| --- | --- |
| 完整 Wine 和媒体桥接编译、候选归档 | 成功 |
| 脚本与打包回归 | 48 项通过 |
| 归档内 FFmpeg 与 GStreamer 双路径解码 | 32 项通过，0 失败，0 跳过 |
| 新媒体组件、Wine 媒体模块和 loader 的架构、依赖、签名检查 | 102 个原生文件通过 |
| 插件自动发现 | 从候选自身目录加载，0 个黑名单插件 |
| 无开发 SDK、无插件路径覆盖的 AV1 自动解码 | 实际输出 3 帧 |
| 归档 SHA-256、清单版本和 ABI | 一致 |
| GLib 对 `pipe2` 的依赖 | 无，保留 `pipe` / `fcntl` |
| Runtime preflight、`git diff --check` | 通过 |

32 项包括 20 种编码样本、11 项额外封装和 1 项 MP4 音视频双流测试。视频覆盖 H.264、HEVC、VP8、VP9、AV1、MPEG-2、MPEG-4、MJPEG、WMV1；音频覆盖 AAC、MP3、Vorbis、Opus、FLAC、PCM、AC-3、E-AC-3、WMA1、WMA2、ALAC。

样本在本机生成，不下载第三方视频。实际解码使用归档内的程序和库，要求产生真实帧/音频数据；双流样本分别检查视频和音频。完整测试使用带空格的解压路径，并临时移走开发 SDK 后运行，结束后已恢复 SDK。另在不设置 GStreamer 插件搜索路径、扫描器路径或动态库覆盖的情况下验证自动发现与 AV1 解码。

## 可复查记录

- `work/media-validation-final/media-decode-report.json`：逐项命令、输出和解码结果。
- `work/media-validation-final/native-audit.json`：归档、102 个原生文件、架构、相对依赖及签名结果。
- `work/media-portability-final/`：隔离 SDK 时的插件发现、黑名单和 AV1 输出记录。

本次执行的核心命令：

```sh
JOBS=3 RUNTIME_CODESIGN_IDENTITY=- nice -n 15 ./script/build-runtime.sh \
  --base-archive dist/arclume-wine-1.1.2-x86_64.tar.xz --channel prerelease
python3 -m unittest discover -s tests -p 'test_*media*.py'
nice -n 15 python3 script/test-media-decode.py \
  --runtime 'work/build/runtime-staging.final check-20260927/arclume-wine-runtime-x86_64' \
  --output-dir work/media-validation-final \
  --fixture-ffmpeg /opt/homebrew/bin/ffmpeg --timeout 60
./script/runtime-preflight.sh
git diff --check
```

再次运行测试需指定尚不存在的输出目录；已有报告不覆盖。构建过程先发现 AV1 被 `DECODE_ONLY` 标记吞帧，再验证并加入限定于 libdav1d 的修复；最终包已包含该补丁。打包检查还拦截了增量构建残留的旧 SDK 链接，重新链接后通过全部验证。

## 未验证与影响范围

测试机为 Apple Silicon / macOS 27，未在 macOS 26 上运行。Wine loader 的部署目标仍为 10.15，但这不等于已经完成旧系统验收。

没有启动 Wine、游戏或任何用户容器；没有视频窗口、声音输出或麦克风调用。游戏内 Media Foundation / DirectShow、启动动画和具体游戏的完整播放流程尚未验证，也不宣称支持全部格式、DRM 或硬件解码。

未改 App 资源清单，未替换 `/Applications` 或已安装运行时，未迁移用户数据，未上传 OSS、提交、推送或发布。原有 1.1.2 保持不动；需要回退时继续使用原运行时即可。后续分发还需完成对应源码、许可与正式签名审核。
