# 多媒体候选构建与验收

## 范围

只修改独立 Runtime 项目。macOS 宿主保持 x86_64，Windows 模块仍成对构建 i386 / x86_64，保留现有游戏容器 ABI。

`sources/MEDIA_SOURCES.json` 固定源码 URL、版本和 SHA-256。`script/build-media.py` 使用独立前缀，禁止 Meson 自动获取未锁定子项目，不链接开发机的 Homebrew 编解码库。构建需要 Python 3.12+、Xcode Command Line Tools、Meson、Ninja、pkg-config、Bison、MinGW 和现有构建所需的 FreeType 头文件；Apple Silicon 需要已安装的 Rosetta。

## 构建

```sh
nice -n 15 python3 script/build-media.py --jobs 3
JOBS=3 RUNTIME_CODESIGN_IDENTITY=- nice -n 15 ./script/build-runtime.sh \
  --base-archive dist/arclume-wine-1.1.2-x86_64.tar.xz \
  --channel prerelease
```

源码下载后逐文件检查哈希。`--cache-seed` 可复用已有源码归档，仍逐文件校验；不复用其他产品的构建结果。构建配方更改后使用新的 SDK 目录，已有成功 SDK 不覆盖。Wine 配置指纹覆盖源码锁、补丁、编译器、SDK 与配置参数；不匹配时需要显式 `--clean`，仅清理本仓库的候选构建目录。

新版本不能使用 `--repackage` 绕过 Wine 桥接模块编译。打包将依赖改为相对路径，检查架构与外部依赖，附带锁文件和许可声明；归档与清单先在临时目录生成，再以不覆盖已有文件的方式发布到本地输出目录。`-` 是本地临时签名，不是发布签名或公证。

## 命令行验收

```sh
python3 -m unittest discover -s tests -p 'test_*media*.py'
./script/runtime-preflight.sh
```

使用 `script/test-media-decode.py --help` 查看测试入口。测试使用单独目录、注册表和本地短样本，将解码结果送往空输出，不打开视频窗口、不播放声音、不启动 Wine 或操作用户容器。FFmpeg / GStreamer 任一路失败都应单独报告；本机缺少样本编码器应记为跳过，不算成功。

```sh
nice -n 15 python3 script/test-media-decode.py \
  --runtime /path/to/extracted/arclume-wine-runtime-x86_64 \
  --output-dir work/media-validation-new \
  --fixture-ffmpeg /path/to/host/ffmpeg --timeout 60
```

样本生成使用宿主 FFmpeg；实际解码只使用候选包中的 FFmpeg 与 GStreamer。矩阵包含 H.264、HEVC、VP8/VP9、AV1、MPEG-2/4、MJPEG、WMV，以及 AAC、MP3、Vorbis、Opus、FLAC、PCM、AC-3、E-AC-3、WMA1/2、ALAC；另覆盖 MP4、MOV、MPEG-TS、AVI、ASF、Ogg、WAV、M4A 等封装，以及 MP4 音视频双流。每项要求真实输出帧/音频数据，不能只凭程序成功退出判定通过。CI 在发布前运行该矩阵，失败或跳过均阻止发布并保存 JSON 报告。

还需在移动后的候选运行时中清除开发机插件路径后检查插件自动发现，防止只因开发 SDK 在原路径而通过测试。

## 兼容性与回退

GStreamer 插件与 FFmpeg 库跟随候选归档，不写入全局插件目录。既有已安装 1.1.2 与游戏数据保持不动。最终游戏视频验证应在用户允许后进行：优先覆盖启动动画、内嵌网页视频、Media Foundation 和 DirectShow，不把原生命令行解码通过等同于 Windows 播放接口全部兼容。

GLib 使用 `pipe + fcntl`，不根据 macOS 27 SDK 的符号误启用 `pipe2`。gst-libav 只对白名单中的软件 `libdav1d` 解码器开放注册，仍排除其余外部库和硬件解码器。libdav1d 自行分配画面，不经过 gst-libav 清除 `DECODE_ONLY` 的回调；补丁在其实际解出帧后清除此标记，避免已解码却没有输出画面。MJPEG 补齐 `jpegparse` 前置解析。

本配置优先覆盖游戏常见的无 DRM 软件解码；没有启用 FFmpeg 网络输入或依赖自动探测，不承诺所有可选外部编解码库、硬件加速、受保护媒体或所有压缩图像格式均可用。列表以实际测试报告为准。

## 发布边界

FFmpeg 配置禁用 GPL / nonfree 选项；这不等于所有格式无专利或分发限制。1.1.3 发布附带已校验的 Wine / 媒体输入归档、对应提交的补丁和构建说明。签名类型、未完成的游戏与系统验收以该版本发布说明为准。2026-09-27 的候选报告保留为历史验收记录，不代表当时已经发布。
