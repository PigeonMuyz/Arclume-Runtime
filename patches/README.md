# Wine 补丁

`work/wine/` 是本机提取后的 Wine 工作树（约 332 MB），因此被 Git 忽略。任何需要随 Arclume 发布的 Wine 源码修改，都应整理为按序号命名的统一 diff 并提交到本目录，例如：

```text
0001-fix-jx3-window-title.patch
```

需要还原到锁定版本并重新应用已提交补丁时，执行：

```bash
./script/sync_crossover_wine_source.sh --reset
```

同步脚本会按照文件名字典序应用所有 `*.patch`。先在工作树中试改、验证；确认要保留的改动后，再将其整理为补丁提交，避免直接依赖未追踪工作树中的修改。
