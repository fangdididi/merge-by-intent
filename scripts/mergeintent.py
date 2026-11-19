#!/usr/bin/env python3
"""merge-by-intent helper: scan conflict hunks, cross-check renames, gate a resolution ledger.

Subcommands
  scan  FILE... [--json]          parse conflict markers, classify every hunk, suggest a move
  cross BASE OURS THEIRS [--repo D] names one side removed that the other side still adds
  gate  LEDGER.json [--json]      lint a resolution ledger -> READY / FIX / HOLD (exit 0/1/2)
Standard library only.
"""
import argparse, fnmatch, json, os, re, subprocess, sys

REGEN_GLOBS = [
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock",
    "Cargo.lock", "poetry.lock", "uv.lock", "Pipfile.lock", "go.sum", "Gemfile.lock", "composer.lock",
    "Podfile.lock", "pubspec.lock", "flake.lock", "*.min.js", "*.min.css", "*.pb.go", "*_pb2.py",
    "*.generated.*", "*.g.dart", "*.snap", "dist/*", "build/*", "*/dist/*", "*/build/*",
]

START, BASE, MID, END = "<<<<<<<", "|||||||", "=======", ">>>>>>>"


def is_regen(path):
    p = path.replace(os.sep, "/")
    name = p.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, g) or fnmatch.fnmatch(p, g) for g in REGEN_GLOBS)


def parse(text):
    """Return list of hunks: dict(line, ours, base, theirs). base is None for 2-way markers."""
    hunks, state, cur = [], None, None
    for no, line in enumerate(text.splitlines(), 1):
        if line.startswith(START) and state is None:
            cur = {"line": no, "ours": [], "base": None, "theirs": []}
            state = "ours"
        elif line.startswith(BASE) and state == "ours":
            cur["base"] = []
            state = "base"
        elif line.startswith(MID) and state in ("ours", "base") and line.strip() == MID:
            state = "theirs"
        elif line.startswith(END) and state == "theirs":
            hunks.append(cur)
            state, cur = None, None
        elif state:
            cur[state].append(line)
    if state:
        cur["broken"] = True
        hunks.append(cur)
    return hunks


def _norm(lines):
    return [re.sub(r"\s+", " ", l).strip() for l in lines if l.strip()]


def _subseq(small, big):
    it = iter(big)
    return all(any(x == y for y in it) for x in small)


def classify(path, h):
    """Return (kind, move, suggestion_lines_or_None)."""
    o, b, t = h["ours"], h["base"], h["theirs"]
    if h.get("broken"):
        return "BROKEN", "repair markers by hand, then rescan", None
    if is_regen(path):
        return "REGEN", "do not hand-merge; take one side, rerun the generator/package manager", None
    if o == t:
        return "SAME", "both sides made the same edit; keep it once", o
    if b is None:
        return "NOBASE", "re-create with base shown: git checkout --conflict=zdiff3 -- " + path, None
    if o == b:
        return "ONE-SIDED", "only theirs changed this region; take theirs", t
    if t == b:
        return "ONE-SIDED", "only ours changed this region; take ours", o
    if _norm(o) == _norm(t):
        return "SPACING", "same content, different whitespace; keep the formatter's version", o
    if not _norm(o) or not _norm(t):
        return "DELETE-VS-EDIT", "one side removed what the other edited; decide from intent", None
    if _subseq(b, o) and _subseq(b, t):
        added_o = [l for l in o if l not in b]
        added_t = [l for l in t if l not in b and l not in o]
        if len(o) - len(b) == len(added_o) and len(t) - len(b) >= len(added_t):
            merged = list(o) + added_t
            return "BOTH-ADD", "both only added lines; keep both, check order and duplicates", merged
    return "TRUE", "both sides changed the same lines differently; write intent cards", None


def cmd_scan(args):
    out, markers = [], 0
    for f in args.files:
        try:
            text = open(f, encoding="utf-8", errors="replace").read()
        except OSError as e:
            print(f"cannot read {f}: {e}", file=sys.stderr)
            continue
        for i, h in enumerate(parse(text), 1):
            markers += 1
            kind, move, sug = classify(f, h)
            out.append({"id": f"{f}#{i}", "file": f, "line": h["line"], "kind": kind, "move": move,
                        "ours_lines": len(h["ours"]), "theirs_lines": len(h["theirs"]),
                        "has_base": h["base"] is not None, "suggestion": sug})
    if args.json:
        print(json.dumps({"hunks": out, "count": markers}, indent=1, ensure_ascii=False))
    else:
        if not out:
            print("no conflict markers found")
        tally = {}
        for x in out:
            tally[x["kind"]] = tally.get(x["kind"], 0) + 1
            print(f"{x['id']:<40} L{x['line']:<5} {x['kind']:<15} {x['move']}")
        if tally:
            print("tally: " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    return 1 if markers else 0


IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
STOP = set("""self this that true false none null return import from class def function const
let var async await public private static void string number boolean export default with
while break continue elif else then else""".split())


def _diff(repo, a, b):
    r = subprocess.run(["git", "-C", repo, "diff", "-U0", "--no-color", a, b], capture_output=True, text=True)
    if r.returncode not in (0, 1):
        raise SystemExit("git diff failed: " + r.stderr.strip())
    plus, minus = [], []
    for line in r.stdout.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            plus.append(line[1:])
        elif line.startswith("-"):
            minus.append(line[1:])
    return plus, minus


def _idents(lines):
    s = set()
    for l in lines:
        s.update(m for m in IDENT.findall(l) if m.lower() not in STOP)
    return s


def gone_names(plus, minus):
    return _idents(minus) - _idents(plus)


def cross_from_diffs(ours_pm, theirs_pm):
    risks = []
    for side, (p, m), other_name, (op, _) in (("ours", ours_pm, "theirs", theirs_pm),
                                             ("theirs", theirs_pm, "ours", ours_pm)):
        added_other = _idents(op)
        for name in sorted(gone_names(p, m) & added_other):
            risks.append({"symbol": name, "removed_by": side, "still_used_by": other_name, "status": "open"})
    return risks


def cmd_cross(args):
    ours = _diff(args.repo, args.base, args.ours)
    theirs = _diff(args.repo, args.base, args.theirs)
    risks = cross_from_diffs(ours, theirs)
    if args.json:
        print(json.dumps({"semantic_risks": risks}, indent=1))
    else:
        if not risks:
            print("no removed-on-one-side / added-on-the-other names found (this is a hint, not proof)")
        for r in risks:
            print(f"RISK {r['symbol']}: removed or renamed by {r['removed_by']}, newly used by {r['still_used_by']}")
    return 1 if risks else 0


RESOLUTIONS = {"OURS", "THEIRS", "BOTH", "BLEND", "NEW", "REGEN", "DROP"}


def lint(ledger):
    finds = []
    add = lambda code, sev, msg: finds.append({"code": code, "sev": sev, "msg": msg})
    if ledger.get("markers_left", 0):
        add("M01", "HOLD", f"{ledger['markers_left']} conflict marker block(s) still in the tree")
    if not ledger.get("backup_ref"):
        add("M08", "FIX", "no backup ref recorded before resolving (e.g. git branch backup/pre-merge)")
    if ledger.get("operation") in ("rebase", "cherry-pick", "revert") and not ledger.get("sides"):
        add("M09", "FIX", "rebase/cherry-pick swaps 'ours' and 'theirs'; write which side is which in 'sides'")
    if ledger.get("pushed"):
        add("M10", "HOLD", "result was pushed before the gate passed")
    for h in ledger.get("hunks", []):
        hid, kind, res = h.get("id", "?"), h.get("kind", ""), str(h.get("resolution", "")).upper()
        if res not in RESOLUTIONS:
            add("M11", "FIX", f"{hid}: resolution '{res or '-'}' is not one of {sorted(RESOLUTIONS)}")
        if kind in ("TRUE", "DELETE-VS-EDIT", "NOBASE"):
            if not h.get("ours_intent") or not h.get("theirs_intent"):
                add("M02", "HOLD", f"{hid}: {kind} hunk without both intents written down")
            if res in ("OURS", "THEIRS", "DROP") and not h.get("dropped_because"):
                add("M03", "FIX", f"{hid}: one side's intent was dropped without 'dropped_because'")
        if kind == "REGEN" and res != "REGEN":
            add("M04", "HOLD", f"{hid}: generated/lock file was hand-merged; regenerate it instead")
        if res in ("NEW", "BLEND") and not h.get("proof"):
            add("M07", "FIX", f"{hid}: {res} wrote code neither side had, but names no check that covers it")
    checks = ledger.get("checks", [])
    ran = [c for c in checks if c.get("result") in ("pass", "fail")]
    if not ran:
        add("M05", "FIX", "no build/test/lint command was run after resolving")
    for c in checks:
        if c.get("result") == "fail":
            add("M06", "HOLD", f"check failed: {c.get('cmd', '?')}")
    for r in ledger.get("semantic_risks", []):
        if r.get("status", "open") == "open":
            add("M12", "FIX", f"semantic risk '{r.get('symbol')}' still open (removed by one side, used by the other)")
    sevs = {f["sev"] for f in finds}
    gate = "HOLD" if "HOLD" in sevs else ("FIX" if "FIX" in sevs else "READY")
    return gate, finds


def cmd_gate(args):
    ledger = json.load(open(args.ledger, encoding="utf-8"))
    gate, finds = lint(ledger)
    if args.json:
        print(json.dumps({"gate": gate, "findings": finds}, indent=1, ensure_ascii=False))
    else:
        for f in finds:
            print(f"{f['code']} {f['sev']:<4} {f['msg']}")
        print("GATE", gate)
    return {"READY": 0, "FIX": 1, "HOLD": 2}[gate]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("files", nargs="+"); s.add_argument("--json", action="store_true")
    c = sub.add_parser("cross"); c.add_argument("base"); c.add_argument("ours"); c.add_argument("theirs")
    c.add_argument("--repo", default="."); c.add_argument("--json", action="store_true")
    g = sub.add_parser("gate"); g.add_argument("ledger"); g.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    return {"scan": cmd_scan, "cross": cmd_cross, "gate": cmd_gate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
