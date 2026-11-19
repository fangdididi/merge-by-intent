# merge-by-intent

**English** | [中文](README.zh-CN.md)

> Resolve git conflicts by what each side was trying to do — then prove it before you commit.

`merge-by-intent` is an agent skill for Claude Code, Codex, Cursor and other coding agents. When a merge, rebase or cherry-pick stops with conflicts, it stops the agent from "picking the text that looks right". Every conflict hunk is sorted by kind, the real clashes get a written intent for both sides, generated files are rebuilt instead of hand-edited, names broken across sides are hunted down, and a gate says **READY / FIX / HOLD** before anything is committed or pushed.

## Why

- Agents (and people) tend to keep their own side and quietly drop the other side's reason for a change.
- Lock files merged by hand look fine and install something nobody asked for.
- The worst merges have no conflict markers at all: one branch renamed `load_cfg`, the other added a new call to it.
- In a rebase, "ours" and "theirs" swap meaning, and a lot of wrong resolutions come from that alone.

## Features

- **Seven hunk kinds**: SAME, ONE-SIDED, SPACING, BOTH-ADD, REGEN, DELETE-VS-EDIT, TRUE (plus NOBASE when markers lack the ancestor), each with a default move.
- **Intent cards**: two lines per real clash — what ours wanted, what theirs wanted, with commit ids — and six resolutions: BOTH, BLEND, OURS/THEIRS (with `dropped_because`), NEW, DROP, REGEN.
- **Cross-side name check**: lists names one side removed or renamed that the other side's new lines still use.
- **Ledger + gate**: 12 lint codes (M01–M12) → READY (exit 0), FIX (1), HOLD (2).
- **Safe defaults**: backup ref first, zdiff3 markers, no push or force until READY, ask instead of guess.
- Helper script is pure Python standard library; 20 unit tests.

## Install

Copy the folder into your agent's skills directory:

```bash
# Claude Code (personal)
git clone https://github.com/fangdididi/merge-by-intent ~/.claude/skills/merge-by-intent
# Claude Code (one project)
git clone https://github.com/fangdididi/merge-by-intent .claude/skills/merge-by-intent
# Codex
git clone https://github.com/fangdididi/merge-by-intent ~/.codex/skills/merge-by-intent
# Cursor
git clone https://github.com/fangdididi/merge-by-intent .cursor/skills/merge-by-intent
```

Other agents: point them at `SKILL.md` (or paste it into the system prompt / rules file).

## Usage

Ask your agent things like:

- "The rebase stopped with conflicts. Resolve them with merge-by-intent."
- "Fix the merge conflicts on this PR, but don't push."
- "The merge was clean but tests broke — check for cross-side breaks."

Or run the helper yourself:

```bash
python3 scripts/mergeintent.py scan $(git diff --name-only --diff-filter=U)
python3 scripts/mergeintent.py cross $(git merge-base HEAD MERGE_HEAD) HEAD MERGE_HEAD
python3 scripts/mergeintent.py gate ledger.json
```

## Example

```
$ python3 scripts/mergeintent.py scan examples/conflicted_settings.py
examples/conflicted_settings.py#1  L1   BOTH-ADD   both only added lines; keep both, check order and duplicates
examples/conflicted_settings.py#2  L11  TRUE       both sides changed the same lines differently; write intent cards
examples/conflicted_settings.py#3  L19  ONE-SIDED  only theirs changed this region; take theirs
tally: BOTH-ADD=1, ONE-SIDED=1, TRUE=1
```

The TRUE hunk: `main` raised an upload timeout to 30 s for slow NAS disks; `feature/config-file` made it an environment variable with default 20. The intent cards show it is not a choice: an env var with default **30** keeps both reasons. `examples/ledger.json` records the run and the gate prints `GATE READY`.

## File structure

```
merge-by-intent/
├── SKILL.md                 # skill instructions (English)
├── SKILL.zh-CN.md           # skill instructions (Chinese)
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

## License

MIT © fangdididi
