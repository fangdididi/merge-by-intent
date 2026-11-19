import json, os, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mergeintent as mi

def block(ours, theirs, base=None):
    s = ["<<<<<<< HEAD"] + ours
    if base is not None:
        s += ["||||||| base"] + base
    return "\n".join(s + ["======="] + theirs + [">>>>>>> feature"])

class Parse(unittest.TestCase):
    def test_two_hunks(self):
        t = "a\n" + block(["x"], ["y"], ["w"]) + "\nmid\n" + block(["p"], ["q"]) + "\n"
        h = mi.parse(t)
        self.assertEqual(len(h), 2)
        self.assertEqual(h[0]["base"], ["w"])
        self.assertIsNone(h[1]["base"])
    def test_broken(self):
        h = mi.parse("<<<<<<< HEAD\nx\n=======\ny\n")
        self.assertTrue(h[0].get("broken"))
        self.assertEqual(mi.classify("a.py", h[0])[0], "BROKEN")

class Classify(unittest.TestCase):
    def k(self, ours, theirs, base=None, path="src/a.py"):
        return mi.classify(path, {"ours": ours, "theirs": theirs, "base": base})
    def test_same(self): self.assertEqual(self.k(["x"], ["x"], ["w"])[0], "SAME")
    def test_nobase(self): self.assertEqual(self.k(["x"], ["y"])[0], "NOBASE")
    def test_one_sided(self):
        k, _, sug = self.k(["w"], ["y"], ["w"])
        self.assertEqual((k, sug), ("ONE-SIDED", ["y"]))
    def test_spacing(self): self.assertEqual(self.k(["a  =  1"], ["a = 1"], ["a=2"])[0], "SPACING")
    def test_delete_vs_edit(self): self.assertEqual(self.k([], ["b = 3"], ["b = 2"])[0], "DELETE-VS-EDIT")
    def test_both_add(self):
        k, _, sug = self.k(["import os", "import re"], ["import os", "import json"], ["import os"])
        self.assertEqual(k, "BOTH-ADD")
        self.assertEqual(sug, ["import os", "import re", "import json"])
    def test_true(self): self.assertEqual(self.k(["t = 30"], ["t = 10"], ["t = 20"])[0], "TRUE")
    def test_regen(self): self.assertEqual(self.k(["a"], ["b"], ["c"], path="web/package-lock.json")[0], "REGEN")

class Cross(unittest.TestCase):
    def test_rename_vs_new_use(self):
        ours = (["def fetch_user(uid):"], ["def get_user(uid):"])
        theirs = (["    return get_user(uid).email"], [])
        r = mi.cross_from_diffs(ours, theirs)
        self.assertEqual([x["symbol"] for x in r], ["get_user"])
        self.assertEqual(r[0]["removed_by"], "ours")
    def test_git_repo(self):
        d = tempfile.mkdtemp()
        g = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)
        g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
        open(os.path.join(d, "m.py"), "w").write("def load_cfg():\n    pass\n")
        g("add", "."); g("commit", "-qm", "base"); g("tag", "b")
        open(os.path.join(d, "m.py"), "w").write("def read_config():\n    pass\n")
        g("commit", "-qam", "rename"); g("tag", "o"); g("checkout", "-q", "b")
        open(os.path.join(d, "n.py"), "w").write("x = load_cfg()\n")
        g("add", "."); g("commit", "-qm", "use"); g("tag", "t")
        r = mi.cross_from_diffs(mi._diff(d, "b", "o"), mi._diff(d, "b", "t"))
        self.assertIn("load_cfg", [x["symbol"] for x in r])

class Gate(unittest.TestCase):
    good = {"operation": "merge", "backup_ref": "backup/pre-merge", "markers_left": 0,
            "hunks": [{"id": "a#1", "kind": "TRUE", "ours_intent": "raise timeout for slow disks",
                       "theirs_intent": "make timeout configurable", "resolution": "BLEND",
                       "proof": "pytest tests/test_timeout.py"}],
            "checks": [{"cmd": "pytest", "result": "pass"}], "semantic_risks": []}
    def test_ready(self): self.assertEqual(mi.lint(self.good)[0], "READY")
    def test_markers_hold(self):
        self.assertEqual(mi.lint(dict(self.good, markers_left=2))[0], "HOLD")
    def test_missing_intent_hold(self):
        l = json.loads(json.dumps(self.good)); l["hunks"][0]["theirs_intent"] = ""
        g, f = mi.lint(l)
        self.assertEqual(g, "HOLD"); self.assertIn("M02", [x["code"] for x in f])
    def test_rebase_needs_sides(self):
        g, f = mi.lint(dict(self.good, operation="rebase"))
        self.assertEqual(g, "FIX"); self.assertIn("M09", [x["code"] for x in f])
    def test_lock_hand_merged(self):
        l = json.loads(json.dumps(self.good))
        l["hunks"].append({"id": "yarn.lock#1", "kind": "REGEN", "resolution": "BOTH"})
        self.assertIn("M04", [x["code"] for x in mi.lint(l)[1]])
    def test_no_checks_fix(self):
        self.assertEqual(mi.lint(dict(self.good, checks=[{"cmd": "pytest", "result": "not_run"}]))[0], "FIX")
    def test_open_risk(self):
        g, f = mi.lint(dict(self.good, semantic_risks=[{"symbol": "get_user", "status": "open"}]))
        self.assertEqual(g, "FIX"); self.assertIn("M12", [x["code"] for x in f])
    def test_dropped_without_reason(self):
        l = json.loads(json.dumps(self.good)); l["hunks"][0]["resolution"] = "OURS"
        self.assertIn("M03", [x["code"] for x in mi.lint(l)[1]])

if __name__ == "__main__":
    unittest.main()
