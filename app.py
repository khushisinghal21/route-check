"""RouteCheck demo: type a request and compare the baseline router with RouteCheck.

Run locally:  python app.py   (then open http://localhost:7860)
On Render:    start command `python app.py`; it reads the PORT env var.
"""
import json
import os
from pathlib import Path

import gradio as gr

from routecheck import CLARIFY, KeywordRouter, RouteCheck
from routecheck.tools import TOOL_LABELS

ROOT = Path(__file__).parent
PARAMS = json.load(open(ROOT / "results" / "params.json"))

baseline = KeywordRouter()
router = RouteCheck(**PARAMS, log_path=ROOT / "results" / "demo_audit_log.jsonl")

EXAMPLES = [
    "Draft a follow-up mail to the insurer about the pending claim",
    "Find the training deck on writing client emails",
    "Summarize this email thread for me",
    "Look up the presentation on employee benefits trends",
    "Has claim CLM-48213 been approved yet?",
    "claims policy",
    "email",
]


def describe(tool):
    return f"**{tool}** ({TOOL_LABELS[tool]})"


def run(text):
    text = (text or "").strip()
    if not text:
        return "", "", ""
    b = baseline.route(text)
    d = router.route(text)

    base_md = f"Routes to {describe(b.action)}\n\nIt always picks a tool, even on a guess."
    if d.action == CLARIFY:
        rc_md = f"**Asks instead of guessing:**\n\n> {d.question}"
    else:
        why = f'action phrase "{d.cue_phrase}"' if d.cue else "intent classifier"
        rc_md = f"Routes to {describe(d.action)}\n\nDecided by: {why} · confidence {d.confidence:.2f}"

    top = sorted(d.scores.items(), key=lambda kv: kv[1], reverse=True)[:3]
    log_md = "Audit log entry (scores):\n\n" + "\n".join(f"- {t}: {s:.2f}" for t, s in top)
    return base_md, rc_md, log_md


with gr.Blocks(title="RouteCheck") as demo:
    gr.Markdown(
        "# RouteCheck\n"
        "Routes requests in an enterprise assistant to the right tool. It decides on what the user wants "
        "*done*, not the topic words they mention, and asks a clarifying question when unsure instead of "
        "confidently picking the wrong tool."
    )
    inp = gr.Textbox(label="Request", placeholder="e.g. Draft a follow-up mail to the insurer about the pending claim")
    btn = gr.Button("Route it", variant="primary")
    with gr.Row():
        out_base = gr.Markdown(label="Baseline")
        out_rc = gr.Markdown(label="RouteCheck")
    out_log = gr.Markdown()
    gr.Examples(EXAMPLES, inputs=inp)
    btn.click(run, inp, [out_base, out_rc, out_log])
    inp.submit(run, inp, [out_base, out_rc, out_log])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
