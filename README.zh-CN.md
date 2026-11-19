# merge-by-intent（按意图解决合并冲突）

[English](README.md) | **中文**

> 按双方各自想做的事来解决 git 冲突——并在提交之前证明它。

`merge-by-intent` 是一个适用于 Claude Code、Codex、Cursor 等编程智能体的技能。当 merge、rebase 或 cherry-pick 因冲突停下时，它阻止智能体“挑一段看起来对的文字”了事：每个冲突块先分类，真正的冲突要写下双方意图，生成文件重新生成而不是手改，跨边改名造成的破坏要找出来，最后由闸门给出 **READY / FIX / HOLD**，之后才允许提交或推送。

## 为什么需要

- 智能体（和人）往往保留自己这边，悄悄丢掉另一边改动的理由。
- 手工合并的锁文件看着没问题，装出来的却是谁也没要的版本。
- 最糟的合并根本没有冲突标记：一个分支把 `load_cfg` 改了名，另一个分支新加了对它的调用。
- rebase 时 “ours” 和 “theirs” 的含义是反的，很多错误解决就出在这里。

## 功能

- **七种冲突块类型**：SAME、ONE-SIDED、SPACING、BOTH-ADD、REGEN、DELETE-VS-EDIT、TRUE（标记缺少祖先段时另有 NOBASE），每种都有默认处理。
- **意图卡**：每个真冲突写两行——ours 想要什么、theirs 想要什么，附提交号；六种解法：BOTH、BLEND、OURS/THEIRS（需写 `dropped_because`）、NEW、DROP、REGEN。
- **跨边名字检查**：列出一边删除或改名、另一边新代码却仍在使用的名字。
- **台账 + 闸门**：12 条检查（M01–M12）→ READY（退出码 0）、FIX（1）、HOLD（2）。
- **安全默认**：先建备份引用、使用 zdiff3 标记、READY 前不推送不强推、拿不准就问而不猜。
- 辅助脚本只用 Python 标准库，附 20 个单元测试。

## 安装

把整个文件夹放进智能体的技能目录：

```bash
# Claude Code（个人）
git clone https://github.com/fangdididi/merge-by-intent ~/.claude/skills/merge-by-intent
# Claude Code（单个项目）
git clone https://github.com/fangdididi/merge-by-intent .claude/skills/merge-by-intent
# Codex
git clone https://github.com/fangdididi/merge-by-intent ~/.codex/skills/merge-by-intent
# Cursor
git clone https://github.com/fangdididi/merge-by-intent .cursor/skills/merge-by-intent
```

其他智能体：让它读取 `SKILL.zh-CN.md` / `SKILL.md`，或把内容粘贴到系统提示词 / 规则文件中。

## 使用

可以这样对智能体说：

- “rebase 冲突停住了，用 merge-by-intent 解决。”
- “把这个 PR 的合并冲突修好，但不要推送。”
- “合并没冲突但测试挂了——查一下跨边破坏。”

也可以自己运行辅助脚本：

```bash
python3 scripts/mergeintent.py scan $(git diff --name-only --diff-filter=U)
python3 scripts/mergeintent.py cross $(git merge-base HEAD MERGE_HEAD) HEAD MERGE_HEAD
python3 scripts/mergeintent.py gate ledger.json
```

## 示例

```
$ python3 scripts/mergeintent.py scan examples/conflicted_settings.py
examples/conflicted_settings.py#1  L1   BOTH-ADD   both only added lines; keep both, check order and duplicates
examples/conflicted_settings.py#2  L11  TRUE       both sides changed the same lines differently; write intent cards
examples/conflicted_settings.py#3  L19  ONE-SIDED  only theirs changed this region; take theirs
tally: BOTH-ADD=1, ONE-SIDED=1, TRUE=1
```

那个 TRUE 冲突：`main` 为了慢速 NAS 硬盘把上传超时调到 30 秒；`feature/config-file` 把它改成环境变量、默认 20。写完意图卡就知道不必二选一：用环境变量、默认值 **30**，两边的理由都保住。`examples/ledger.json` 记录了这次处理，闸门输出 `GATE READY`。

## 文件结构

```
merge-by-intent/
├── SKILL.md                 # 技能说明（英文）
├── SKILL.zh-CN.md           # 技能说明（中文）
├── README.md
├── README.zh-CN.md
├── LICENSE
├── scripts/
│   └── mergeintent.py       # scan / cross / gate
├── tests/
│   └── test_mergeintent.py  # python3 -m unittest discover -s tests
└── examples/
    ├── conflicted_settings.py
    └── ledger.json
```

## 许可证

MIT © fangdididi
