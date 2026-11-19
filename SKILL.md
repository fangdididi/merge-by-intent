---
name: merge-by-intent
description: Resolve git merge, rebase and cherry-pick conflicts by what each side was trying to do, not by which text looks newer. Sorts every conflict hunk into seven kinds, writes a two-line intent card for the real clashes, hunts for "clean" merges that still break (a name renamed on one side and newly used on the other), regenerates lock files instead of hand-editing them, and gates the result READY / FIX / HOLD before anything is committed or pushed. Use when a branch has conflicts, a rebase stopped, or an agent is asked to "fix the merge conflicts".
---

# merge-by-intent

**Language:** English | [中文](SKILL.zh-CN.md)

## What this is

A conflict is two people (or two agents) who each wanted something. Git only shows you the text they left behind. The usual failure is picking the text that "looks right" — often the side you wrote — and silently throwing away the other side's reason for changing that line. The second usual failure is a merge with **no** conflict markers that still breaks, because one side renamed a function while the other side added a new call to the old name.

This skill makes the agent do three things in order:

1. **Sort** every conflict hunk by kind, so the easy ones are settled mechanically and attention goes to the real clashes.
2. **Read intent** for each real clash from the commits that touched it, write it down for both sides, and write a resolution that keeps both intents (or says why one was dropped).
3. **Prove** the result: no markers left, generated files regenerated, cross-side name breaks checked, build and tests run — then a gate says READY, FIX or HOLD.

## When to use

- `git merge`, `git rebase`, `git cherry-pick`, `git revert` or `git stash pop` stopped with conflicts.
- A pull request says "This branch has conflicts that must be resolved".
- You are about to say "just take ours" for a whole file.
- A merge went through cleanly but the build or tests broke right after.

Not for: deciding *whether* to merge a branch (that is review), or rewriting history that others already pulled.

## Ground rules

- **Back up first.** `git branch backup/pre-merge-<date>` (or note `ORIG_HEAD`). You can always `git merge --abort` / `git rebase --abort`.
- **Know which side is which.** In a merge, *ours* = the branch you are on, *theirs* = the branch coming in. In a **rebase** it is flipped: *ours* = the upstream you are replaying onto, *theirs* = your own commit being replayed. Write the mapping down before touching anything.
- **Always see the base.** Turn on three-way markers: `git config merge.conflictStyle zdiff3` (git ≥ 2.35; use `diff3` on older git). For an already-conflicted file: `git checkout --conflict=zdiff3 -- <file>`.
- **Never hand-merge generated files** (lock files, minified bundles, protobuf output, snapshots). Take one side, then run the tool that produces them.
- **No push, tag or force until the gate says READY.** Resolution stays local.
- **Keep the diff small.** No refactors, renames or formatting sweeps while resolving.

## Step by step

### Step 1 — Freeze the scene

```bash
git status --short            # UU = both modified, AA = both added, UD/DU = modify vs delete
git branch backup/pre-merge-$(date +%F)
git config merge.conflictStyle zdiff3
git config rerere.enabled true  # optional: git remembers resolutions you repeat
```

Record in the ledger: operation (merge/rebase/...), which side is ours and which is theirs, backup ref.

### Step 2 — Sort the hunks

```bash
python3 scripts/mergeintent.py scan $(git diff --name-only --diff-filter=U)
```

Each hunk gets one kind:

| Kind | What it means | Default move |
|---|---|---|
| SAME | both sides made the identical change | keep it once |
| ONE-SIDED | one side equals the base; only the other changed | take the changed side |
| SPACING | same content, whitespace differs | keep the formatter's version |
| BOTH-ADD | both only added lines around a shared base (imports, list entries, routes) | keep both; fix order and duplicates |
| REGEN | lock file or generated output | take either side, rerun the generator |
| DELETE-VS-EDIT | one side removed what the other edited | decide from intent (Step 3) |
| TRUE | both changed the same lines in different ways | intent cards (Step 3) |
| NOBASE | markers have no base section | re-checkout with zdiff3 and rescan |

Also check file-level conflicts in `git status`: `UD`/`DU` (modified on one side, deleted on the other) and rename/rename always count as DELETE-VS-EDIT or TRUE.

### Step 3 — Write intent cards for the hard ones

For every TRUE, DELETE-VS-EDIT or file-level conflict:

```bash
git log --merge --oneline -- <file>         # commits on both sides that touched the file
git log --merge -p -- <file>                 # with diffs
git log -L <start>,<end>:<file> <side>       # history of just these lines on one side
```

Read commit messages, linked issues and PR descriptions. Write two lines:

- **ours wanted:** *upload timeout 30 s because NAS disks timed out at 20 (a1b2c3d)*
- **theirs wanted:** *timeout configurable from the environment (9f8e7d6)*

Then pick one resolution:

| Resolution | Use when |
|---|---|
| BOTH | the two changes are independent and can sit side by side |
| BLEND | one new line satisfies both intents (env var with 30 as default) |
| OURS / THEIRS | one intent is obsolete — write `dropped_because` |
| NEW | neither text works and you wrote something new — needs a test that covers it |
| DROP | both sides' code should go (rare) — write why |
| REGEN | generated file, rebuilt by its tool |

If you cannot tell what one side wanted, **stop and ask** the author rather than guess. That is a HOLD, not a FIX.

### Step 4 — Hunt for breaks without markers

Git only flags overlapping lines. Check what each side removed that the other side newly uses:

```bash
python3 scripts/mergeintent.py cross $(git merge-base HEAD MERGE_HEAD) HEAD MERGE_HEAD
```

(During a rebase, use `REBASE_HEAD` / the onto commit.) Each RISK is a name one side deleted or renamed that the other side's new lines still use. Fix it or mark it checked. This is a text heuristic: the compiler, type checker and tests are the real proof.

Other quiet breaks worth a glance: two migrations with the same number, two new config keys with the same name, a function signature changed on one side while the other added a caller, and duplicated entries in registries.

### Step 5 — Regenerate, then run the checks

```bash
git checkout --theirs package-lock.json && npm install     # or: pnpm install, cargo update -w, uv lock, go mod tidy ...
rg -n '^(<<<<<<<|\|\|\|\|\|\|\||=======|>>>>>>>)' .           # must print nothing
<build>  <type-check>  <tests that touch the changed files>
```

Record each command and pass/fail in the ledger.

### Step 6 — Gate

Fill `ledger.json` (see `examples/ledger.json`) and run:

```bash
python3 scripts/mergeintent.py gate ledger.json     # exit 0 READY, 1 FIX, 2 HOLD
```

| Code | Gate | Finding |
|---|---|---|
| M01 | HOLD | conflict markers still in the tree |
| M02 | HOLD | a TRUE / DELETE-VS-EDIT / NOBASE hunk without both intents written |
| M03 | FIX | one side's intent dropped without `dropped_because` |
| M04 | HOLD | a generated or lock file was hand-merged |
| M05 | FIX | no build/test/lint was run |
| M06 | HOLD | a check failed |
| M07 | FIX | NEW or BLEND code with no named check covering it |
| M08 | FIX | no backup ref |
| M09 | FIX | rebase/cherry-pick/revert without the ours/theirs mapping written |
| M10 | HOLD | pushed before the gate passed |
| M11 | FIX | resolution value missing or unknown |
| M12 | FIX | cross-side name risk still open |

Only on READY: `git add` the files, then `git merge --continue` / `git rebase --continue`. Do not push unless the user asked.

### Step 7 — Report

Short and checkable:

```
Merge main <- feature/config-file: READY
3 hunks: 1 BOTH-ADD kept both, 1 ONE-SIDED took theirs, 1 TRUE blended
  settings.py#2 timeout: ours=30 s for slow NAS, theirs=env-configurable -> env var, default 30
Cross-side: load_cfg renamed by main, new call in cli.py updated
Checks: compileall pass, pytest pass, no markers
Backup: backup/pre-merge-2026-11-19
```

## Example

`examples/conflicted_settings.py` holds three hunks. `scan` sorts them as BOTH-ADD (two new imports), TRUE (timeout 30 vs. environment variable) and ONE-SIDED (only the incoming branch changed `retries()`). The intent cards show that the TRUE hunk is not a choice at all: the env-var line with `"30"` as default keeps both reasons. `examples/ledger.json` records it and gates READY.

## Tips

- A file that conflicts on every rebase step is a sign to squash your own commits first, or to merge instead of rebase.
- `git rerere` replays a resolution you already made; check its output like any other hunk.
- `git checkout --ours/--theirs <file>` takes a whole side. Fine for REGEN files; for source files it must still pass Step 3.
- Many conflicts in one file after a formatter run on one side: re-run the same formatter on the other side first, then merge again.
- When the agent is not sure, the cheapest move is `git merge --abort` and a question — not a guess.
