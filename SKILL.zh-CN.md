---
name: merge-by-intent
description: 按双方各自“想做什么”来解决 git merge / rebase / cherry-pick 冲突，而不是看哪段文字更新。把每个冲突块分成七类，对真正的冲突写下双方意图卡，排查“没有冲突标记却会坏”的情况（一边改了名、另一边新增了对旧名字的调用），锁文件一律重新生成而不手改，最后在提交或推送前给出 READY / FIX / HOLD 闸门结论。适用于分支有冲突、rebase 中断，或让智能体“把合并冲突修一下”的时候。
---

# merge-by-intent（按意图解决合并冲突）

**语言：** [English](SKILL.md) | 中文

## 这是什么

冲突的本质是两个人（或两个智能体）各自想要一样东西，而 git 只给你看他们留下的文字。最常见的翻车是挑一段“看起来对”的文字——往往是自己写的那边——然后悄悄丢掉了另一边改这一行的理由。第二常见的翻车是合并**没有**任何冲突标记，结果还是坏了：一边把函数改了名，另一边又新加了对旧名字的调用。

这个技能让智能体按顺序做三件事：

1. **分类**：给每个冲突块定性，简单的机械处理掉，注意力留给真正的冲突。
2. **读意图**：从改动过这些行的提交里，分别写下双方想做什么，再写出同时满足两边意图的解法（或者写明为什么放弃其中一边）。
3. **证明**：没有残留标记、生成文件已重新生成、跨边改名风险已检查、构建和测试已跑过——最后闸门给出 READY、FIX 或 HOLD。

## 什么时候用

- `git merge`、`git rebase`、`git cherry-pick`、`git revert` 或 `git stash pop` 因冲突停下。
- PR 页面提示“This branch has conflicts that must be resolved”。
- 你正准备对整个文件说“直接用我们这边”。
- 合并很顺利，没有冲突，但构建或测试紧接着就挂了。

不适用于：判断*要不要*合并某个分支（那是代码评审），或改写别人已经拉取过的历史。

## 基本规则

- **先备份。** `git branch backup/pre-merge-<日期>`（或记下 `ORIG_HEAD`）。随时可以 `git merge --abort` / `git rebase --abort`。
- **分清哪边是哪边。** merge 时，*ours* = 当前所在分支，*theirs* = 合进来的分支。**rebase 时正好相反**：*ours* = 你要变基到的上游，*theirs* = 正在重放的你自己的提交。动手前先把对应关系写下来。
- **永远看到共同祖先。** 开启三方标记：`git config merge.conflictStyle zdiff3`（git ≥ 2.35；更老的版本用 `diff3`）。已经冲突的文件可以用 `git checkout --conflict=zdiff3 -- <文件>` 重新生成标记。
- **生成文件绝不手工合并**（锁文件、压缩后的包、protobuf 产物、快照）。任取一边，然后运行生成它的工具。
- **闸门 READY 之前不 push、不打 tag、不强推。** 解决过程只在本地。
- **改动保持最小。** 解决冲突时不顺手重构、改名或全局格式化。

## 操作步骤

### 第 1 步：冻结现场

```bash
git status --short            # UU = 双方都改了，AA = 双方都新增，UD/DU = 一边改一边删
git branch backup/pre-merge-$(date +%F)
git config merge.conflictStyle zdiff3
git config rerere.enabled true  # 可选：git 会记住你重复做过的解决方式
```

在台账里记录：操作类型（merge/rebase/……）、哪边是 ours 哪边是 theirs、备份引用。

### 第 2 步：给冲突块分类

```bash
python3 scripts/mergeintent.py scan $(git diff --name-only --diff-filter=U)
```

每个冲突块归入一类：

| 类别 | 含义 | 默认处理 |
|---|---|---|
| SAME | 双方做了完全相同的修改 | 保留一份 |
| ONE-SIDED | 一边与祖先相同，只有另一边改了 | 取改动的那一边 |
| SPACING | 内容相同，只有空白不同 | 保留格式化工具的版本 |
| BOTH-ADD | 双方都只是在共同内容旁新增行（import、列表项、路由） | 两边都留，理顺顺序、去重 |
| REGEN | 锁文件或生成产物 | 任取一边，重新运行生成工具 |
| DELETE-VS-EDIT | 一边删了另一边改过的内容 | 按意图决定（第 3 步） |
| TRUE | 双方以不同方式改了同样的行 | 写意图卡（第 3 步） |
| NOBASE | 标记里没有祖先段 | 用 zdiff3 重新检出后再扫描 |

另外看 `git status` 里的文件级冲突：`UD`/`DU`（一边修改、一边删除）以及双方各自改名，一律按 DELETE-VS-EDIT 或 TRUE 处理。

### 第 3 步：为难点写意图卡

对每个 TRUE、DELETE-VS-EDIT 或文件级冲突：

```bash
git log --merge --oneline -- <文件>         # 两边动过这个文件的提交
git log --merge -p -- <文件>                 # 带差异
git log -L <起>,<止>:<文件> <某一边>         # 只看这几行在某一边的历史
```

读提交信息、关联的 issue 和 PR 描述，写下两行：

- **ours 想要：** *上传超时改成 30 秒，因为 NAS 硬盘在 20 秒时会超时（a1b2c3d）*
- **theirs 想要：** *超时可通过环境变量配置（9f8e7d6）*

然后选一种解法：

| 解法 | 适用情况 |
|---|---|
| BOTH | 两处改动互不相干，可以并存 |
| BLEND | 一行新代码同时满足双方意图（环境变量，默认值 30） |
| OURS / THEIRS | 有一方的意图已经过时——写明 `dropped_because` |
| NEW | 两边的文字都不行，你写了新的——需要有测试覆盖 |
| DROP | 两边的代码都该删（少见）——写明原因 |
| REGEN | 生成文件，由其工具重新生成 |

如果实在看不出某一边想要什么，**停下来问作者**，不要猜。这属于 HOLD，不是 FIX。

### 第 4 步：排查没有冲突标记的破坏

git 只会标出重叠的行。检查一边删掉、另一边却在新代码里使用的名字：

```bash
python3 scripts/mergeintent.py cross $(git merge-base HEAD MERGE_HEAD) HEAD MERGE_HEAD
```

（rebase 期间用 `REBASE_HEAD` 和 onto 提交。）每条 RISK 表示一个名字被一边删掉或改名，另一边新增的代码却还在用。修掉或标记为已检查。这只是文本层面的启发式提示，真正的证明是编译器、类型检查和测试。

其他值得扫一眼的静默破坏：两个编号相同的数据库迁移、两个同名的新配置项、一边改了函数签名而另一边新增了调用、注册表里的重复条目。

### 第 5 步：重新生成，再跑检查

```bash
git checkout --theirs package-lock.json && npm install     # 或 pnpm install、cargo update -w、uv lock、go mod tidy ……
rg -n '^(<<<<<<<|\|\|\|\|\|\|\||=======|>>>>>>>)' .           # 必须没有输出
<构建>  <类型检查>  <涉及改动文件的测试>
```

把每条命令及其通过/失败记进台账。

### 第 6 步：闸门

填写 `ledger.json`（参见 `examples/ledger.json`），然后运行：

```bash
python3 scripts/mergeintent.py gate ledger.json     # 退出码 0 READY，1 FIX，2 HOLD
```

| 代码 | 结论 | 发现 |
|---|---|---|
| M01 | HOLD | 代码树里仍有冲突标记 |
| M02 | HOLD | TRUE / DELETE-VS-EDIT / NOBASE 冲突块没有写全双方意图 |
| M03 | FIX | 丢弃了一方意图却没写 `dropped_because` |
| M04 | HOLD | 手工合并了生成文件或锁文件 |
| M05 | FIX | 没跑任何构建/测试/lint |
| M06 | HOLD | 有检查失败 |
| M07 | FIX | NEW 或 BLEND 写出的代码没有指明覆盖它的检查 |
| M08 | FIX | 没有备份引用 |
| M09 | FIX | rebase/cherry-pick/revert 没写明 ours/theirs 对应关系 |
| M10 | HOLD | 闸门通过前就推送了 |
| M11 | FIX | 解法字段缺失或不认识 |
| M12 | FIX | 跨边改名风险仍未处理 |

只有 READY 时才 `git add` 文件，再 `git merge --continue` / `git rebase --continue`。用户没要求就不要推送。

### 第 7 步：汇报

简短、可核对：

```
合并 main <- feature/config-file：READY
3 个冲突块：1 个 BOTH-ADD 两边保留，1 个 ONE-SIDED 取 theirs，1 个 TRUE 融合
  settings.py#2 超时：ours=为慢速 NAS 改 30 秒，theirs=可用环境变量配置 -> 环境变量，默认 30
跨边检查：main 把 load_cfg 改了名，cli.py 中的新调用已同步
检查：compileall 通过，pytest 通过，无残留标记
备份：backup/pre-merge-2026-11-19
```

## 示例

`examples/conflicted_settings.py` 里有三个冲突块。`scan` 把它们分为 BOTH-ADD（两条新 import）、TRUE（超时 30 对比环境变量）和 ONE-SIDED（只有合入分支改了 `retries()`）。写完意图卡就会发现，那个 TRUE 冲突其实不用二选一：用环境变量、默认值写 `"30"`，两边的理由都保住了。`examples/ledger.json` 记录了这次处理，闸门结果为 READY。

## 小贴士

- 某个文件在 rebase 的每一步都冲突，说明应该先把自己的提交压成一个，或者改用 merge。
- `git rerere` 会重放你做过的解决方式，它的结果也要像其他冲突块一样检查。
- `git checkout --ours/--theirs <文件>` 会整文件取一边。对 REGEN 文件没问题；对源代码文件仍然要过第 3 步。
- 一边跑过格式化导致整文件冲突：先在另一边跑同一个格式化工具，再重新合并。
- 智能体拿不准时，最便宜的做法是 `git merge --abort` 再问一句，而不是猜。
