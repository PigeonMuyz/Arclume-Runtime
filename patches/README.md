# Wine 补丁

`work/wine/` 是本机提取后的 Wine 工作树（约 332 MB），因此被 Git 忽略。任何需要随 Arclume 发布的 Wine 源码修改，都应整理为按序号命名的统一 diff 并提交到本目录，例如：

```text
0001-fix-jx3-window-title.patch
```

需要还原到锁定版本并重新应用已提交补丁时，执行：

```bash
./script/sync-wine-source.sh --reset
```

同步脚本先按文件名字典序应用本目录顶层的本地补丁，再按
[`finewine/PATCH_ORDER`](finewine/PATCH_ORDER) 应用已锁定的 FineWine 补丁集。该补丁集在
同步前会完成 SHA-256 校验；其许可、作者归属和上游修订见
[`finewine/README.md`](finewine/README.md)。

先在工作树中试改、验证；确认要保留的改动后，再将其整理为补丁提交，避免直接依赖未追踪工作树中的修改。
