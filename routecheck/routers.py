"""Routers that decide which tool should handle a request.

KeywordRouter   - baseline. Picks the tool whose description shares the most
                  words with the request. Always routes. This reproduces the
                  classic failure: "Draft an email" matches documents/tools
                  that merely mention "email".
ClassifierRouter - TF-IDF + logistic regression trained on canonical
                  utterances. Always routes (ablation).
RouteCheck      - classifier + action cues (what the user wants DONE, taken
                  from the earliest action phrase) + a confidence gate that
                  asks a clarifying question instead of guessing, + an audit
                  log of every decision.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import FeatureUnion, Pipeline

from .tools import TOOLS, TOOL_NAMES, TOOL_LABELS
from .training_data import TRAINING

CLARIFY = "CLARIFY"


@dataclass
class Decision:
    request: str
    action: str                      # a tool name, or CLARIFY
    scores: dict[str, float]
    confidence: float
    margin: float
    cue: str | None = None           # tool implied by the action phrase, if any
    cue_phrase: str | None = None
    question: str | None = None      # clarifying question, when action == CLARIFY
    options: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Baseline
# --------------------------------------------------------------------------- #
class KeywordRouter:
    name = "Keyword similarity (baseline)"

    def __init__(self):
        self.vec = TfidfVectorizer(stop_words="english")
        self.matrix = self.vec.fit_transform([TOOLS[t] for t in TOOL_NAMES])

    def route(self, text: str) -> Decision:
        sims = cosine_similarity(self.vec.transform([text]), self.matrix)[0]
        scores = {t: float(s) for t, s in zip(TOOL_NAMES, sims)}
        order = sorted(scores, key=scores.get, reverse=True)
        # Always routes, even with zero overlap (falls back to the first tool).
        return Decision(text, order[0], scores, scores[order[0]],
                        scores[order[0]] - scores[order[1]])


# --------------------------------------------------------------------------- #
# Intent classifier
# --------------------------------------------------------------------------- #
def _build_classifier() -> Pipeline:
    texts, labels = [], []
    for tool, utterances in TRAINING.items():
        texts += utterances + [TOOLS[tool].lower()]
        labels += [tool] * (len(utterances) + 1)
    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)),
    ])
    clf = Pipeline([("features", features),
                    ("lr", LogisticRegression(C=10, max_iter=2000))])
    clf.fit(texts, labels)
    return clf


class ClassifierRouter:
    name = "Intent classifier, always routes"

    def __init__(self, clf: Pipeline | None = None):
        self.clf = clf or _build_classifier()

    def probs(self, text: str) -> dict[str, float]:
        p = self.clf.predict_proba([text.lower()])[0]
        return {t: float(v) for t, v in zip(self.clf.classes_, p)}

    def route(self, text: str) -> Decision:
        scores = self.probs(text)
        order = sorted(scores, key=scores.get, reverse=True)
        return Decision(text, order[0], scores, scores[order[0]],
                        scores[order[0]] - scores[order[1]])


# --------------------------------------------------------------------------- #
# Action cues: what does the user want DONE?
# The main action is usually the first action phrase in the request, so the
# earliest match wins. Nouns ("email", "policy", "claim") are NOT cues on
# their own; they say what the request is about, not what to do.
# --------------------------------------------------------------------------- #
_CLAIM_NOUN = r"(claim|reimbursement|payout)"

ACTION_CUES: list[tuple[str, str]] = [
    # draft_email
    ("draft_email", r"\b(draft|compose|write|reply|respond)\b"),
    ("draft_email", r"\b(send|prepare|put together)\b[^.?!]{0,25}\b(e-?mail|mail|note|message)\b"),
    ("draft_email", r"\be-?mail\s+(the|to|my|our|him|her|them|everyone|all)\b"),
    # schedule_meeting (checked before search so "find a slot/time" wins)
    ("schedule_meeting", r"\b(schedule|reschedule|book|arrange|invite|organi[sz]e|block)\b"),
    ("schedule_meeting", r"\bset (up|a)\b[^.?!]{0,40}\b(meeting|call|review|sync|session|walkthrough|1:1)\b"),
    ("schedule_meeting", r"\bfind (a )?(slot|time)\b"),
    ("schedule_meeting", r"\b(move|push|put|add)\b[^.?!]{0,40}\b(meeting|call|calendar|\d{1,2} ?(am|pm))\b"),
    # summarize_document
    ("summarize_document", r"\b(summari[sz]e|summary|tl;?dr|condense|recap|shorten|boil (it |this )?down|break down)\b"),
    ("summarize_document", r"\b(key (points|takeaways)|main (points|takeaways)|takeaways|highlights|in brief|overview)\b"),
    # search_documents
    ("search_documents", r"\b(find|search|locate|look up|pull up|looking for|get (me|us|the)|show me)\b"),
    ("search_documents", r"\bwhere('s| is| are| can i find)\b(?![^.?!]*\b" + _CLAIM_NOUN + r")"),
    # claim_status (only when a claim/reimbursement is actually mentioned)
    ("claim_status", r"\b(status|approved|settled|pending|processed|paid|track|stuck|stage|update on|go(ne)? through|under review)\b"),
    # policy_lookup
    ("policy_lookup", r"\b(covered|cover|eligible|entitled|allowed|how many|how much|limit|policy (on|say)|rules?\b for|can i|do i need|is there a|does (our|the company|the policy))\b"),
]

_COMPILED = [(tool, re.compile(p, re.I)) for tool, p in ACTION_CUES]


def find_action_cue(text: str) -> tuple[str | None, str | None]:
    """Return (tool, phrase) for the earliest action phrase in the request."""
    best = None  # (start, -length, tool, phrase)
    has_claim = re.search(r"\b" + _CLAIM_NOUN + r"s?\b", text, re.I) is not None
    for tool, rx in _COMPILED:
        if tool == "claim_status" and not has_claim:
            continue
        m = rx.search(text)
        if m:
            key = (m.start(), -(m.end() - m.start()))
            if best is None or key < best[:2]:
                best = (*key, tool, m.group(0))
    if best is None:
        return None, None
    return best[2], best[3]


# --------------------------------------------------------------------------- #
# RouteCheck
# --------------------------------------------------------------------------- #
class RouteCheck:
    name = "RouteCheck"

    def __init__(self, min_confidence: float = 0.5, min_margin: float = 0.15,
                 cue_weight: float = 0.5, log_path: str | Path | None = None,
                 clf: Pipeline | None = None, min_words_without_action: int = 4):
        self.classifier = ClassifierRouter(clf)
        self.min_words_without_action = min_words_without_action
        self.min_confidence = min_confidence
        self.min_margin = min_margin
        self.cue_weight = cue_weight
        self.log_path = Path(log_path) if log_path else None

    def route(self, text: str) -> Decision:
        probs = self.classifier.probs(text)
        cue, phrase = find_action_cue(text)
        if cue:
            w = self.cue_weight
            scores = {t: (1 - w) * p + (w if t == cue else 0.0) for t, p in probs.items()}
        else:
            scores = dict(probs)
        order = sorted(scores, key=scores.get, reverse=True)
        conf = scores[order[0]]
        margin = conf - scores[order[1]]

        # A bare noun phrase with no action ("claims", "Monday's meeting") is a
        # topic, not a request: ask rather than guess what to do with it.
        bare_topic = cue is None and len(re.findall(r"[\w']+", text)) < self.min_words_without_action

        if bare_topic or conf < self.min_confidence or margin < self.min_margin:
            options = order[:2]
            question = ("I want to get this right. Would you like me to "
                        f"{TOOL_LABELS[options[0]]} or {TOOL_LABELS[options[1]]}?")
            d = Decision(text, CLARIFY, scores, conf, margin, cue, phrase, question, options)
        else:
            d = Decision(text, order[0], scores, conf, margin, cue, phrase)
        self._log(d)
        return d

    def _log(self, d: Decision) -> None:
        if not self.log_path:
            return
        rec = asdict(d)
        rec["ts"] = time.time()
        rec["scores"] = {k: round(v, 4) for k, v in rec["scores"].items()}
        with open(self.log_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
