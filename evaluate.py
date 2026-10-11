"""Evaluate the routers.

    python evaluate.py --tune          # tune RouteCheck thresholds on dev.jsonl only
    python evaluate.py --final         # evaluate all routers once on the held-out test.jsonl

Metrics
-------
Clear requests (one correct tool):
  accuracy            routed to the correct tool
  wrong-tool rate     routed to a WRONG tool (the costly failure)
  clarified           asked a question instead of routing (safe, but a small cost)
Ambiguous requests (no single correct tool):
  clarified           asked a clarifying question (correct behaviour)
  guessed             routed somewhere anyway
Overall:
  confident-wrong     wrong tool on clear requests + guesses on ambiguous ones,
                      over all requests: how often the user gets a confident wrong answer
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

from routecheck import CLARIFY, ClassifierRouter, KeywordRouter, RouteCheck
from routecheck.routers import _build_classifier

ROOT = Path(__file__).parent
DATA = ROOT / "data"
AMB = "AMBIGUOUS"


def load(split):
    return [json.loads(l) for l in open(DATA / f"{split}.jsonl")]


def check_frozen():
    expected = dict(line.split()[::-1] for line in open(DATA / "FROZEN.sha256"))
    for path, digest in expected.items():
        actual = hashlib.sha256(open(ROOT / path, "rb").read()).hexdigest()
        if actual != digest:
            raise SystemExit(f"{path} changed since it was frozen. Refusing to evaluate.")


def score(router, rows):
    clear = [r for r in rows if r["label"] != AMB]
    traps = [r for r in clear if r["trap"]]
    amb = [r for r in rows if r["label"] == AMB]
    decisions = {r["id"]: router.route(r["text"]) for r in rows}

    def frac(subset, pred):
        return sum(pred(r, decisions[r["id"]].action) for r in subset) / len(subset) if subset else 0.0

    right = lambda r, a: a == r["label"]
    wrong = lambda r, a: a not in (r["label"], CLARIFY)
    clar = lambda r, a: a == CLARIFY

    m = {
        "clear_accuracy": frac(clear, right),
        "clear_wrong_tool": frac(clear, wrong),
        "clear_clarified": frac(clear, clar),
        "trap_accuracy": frac(traps, right),
        "trap_wrong_tool": frac(traps, wrong),
        "amb_clarified": frac(amb, clar),
        "amb_guessed": 1 - frac(amb, clar) if amb else 0.0,
    }
    n_wrong = sum(wrong(r, decisions[r["id"]].action) for r in clear)
    n_guess = sum(not clar(r, decisions[r["id"]].action) for r in amb)
    n_right = sum(right(r, decisions[r["id"]].action) for r in clear)
    n_clar_amb = len(amb) - n_guess
    m["confident_wrong"] = (n_wrong + n_guess) / len(rows)
    m["correct_behaviour"] = (n_right + n_clar_amb) / len(rows)
    m["counts"] = {"total": len(rows), "clear": len(clear), "traps": len(traps), "ambiguous": len(amb),
                   "wrong_tool": n_wrong, "guessed": n_guess}
    return m, decisions


def tune(clf):
    dev = load("dev")
    best = None
    grid = itertools.product([0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8],
                             [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4],
                             [0.3, 0.4, 0.5, 0.6, 0.7])
    for c, mg, w in grid:
        m, _ = score(RouteCheck(c, mg, w, clf=clf), dev)
        key = (m["correct_behaviour"], -m["confident_wrong"], -m["clear_clarified"])
        if best is None or key > best[0]:
            best = (key, {"min_confidence": c, "min_margin": mg, "cue_weight": w}, m)
    return best[1], best[2]


def pct(x):
    return f"{100 * x:.0f}%"


def table(results):
    lines = ["| Router | Clear: correct | Clear: wrong tool | Lexical traps: wrong tool | Clear: asked instead | Ambiguous: asked | Confident-wrong (all) |",
             "|---|---|---|---|---|---|---|"]
    for name, m in results.items():
        lines.append(f"| {name} | {pct(m['clear_accuracy'])} | {pct(m['clear_wrong_tool'])} | "
                     f"{pct(m['trap_wrong_tool'])} | {pct(m['clear_clarified'])} | "
                     f"{pct(m['amb_clarified'])} | {pct(m['confident_wrong'])} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args()
    check_frozen()
    clf = _build_classifier()

    params_path = ROOT / "results" / "params.json"
    params_path.parent.mkdir(exist_ok=True)

    if args.tune:
        params, m = tune(clf)
        json.dump(params, open(params_path, "w"), indent=2)
        print("Tuned on dev:", params)
        dev = load("dev")
        res = {"Keyword similarity (baseline)": score(KeywordRouter(), dev)[0],
               "Intent classifier, always routes": score(ClassifierRouter(clf), dev)[0],
               "RouteCheck": m}
        print(table(res))

    if args.final:
        params = json.load(open(params_path))
        test = load("test")
        routers = {"Keyword similarity (baseline)": KeywordRouter(),
                   "Intent classifier, always routes": ClassifierRouter(clf),
                   "RouteCheck": RouteCheck(**params, clf=clf, log_path=ROOT / "results" / "audit_log.jsonl")}
        (ROOT / "results" / "audit_log.jsonl").unlink(missing_ok=True)
        res, per_request = {}, []
        for name, r in routers.items():
            m, dec = score(r, test)
            res[name] = m
            for row in test:
                d = dec[row["id"]]
                per_request.append({"router": name, "id": row["id"], "text": row["text"], "label": row["label"],
                                    "trap": row["trap"], "decision": d.action, "cue": d.cue,
                                    "confidence": round(d.confidence, 3)})
        json.dump({"params": params, "results": res}, open(ROOT / "results" / "test_results.json", "w"), indent=2)
        with open(ROOT / "results" / "test_decisions.jsonl", "w") as f:
            for p in per_request:
                f.write(json.dumps(p) + "\n")
        md = table(res)
        (ROOT / "results" / "test_results.md").write_text(md + "\n")
        print("Params (tuned on dev):", params)
        print(md)
        for name, m in res.items():
            print(name, m["counts"])


if __name__ == "__main__":
    main()
