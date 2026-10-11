# RouteCheck

**Stop an enterprise AI assistant from confidently sending a request to the wrong tool.**

Internal assistants route each request to a tool: draft an email, search documents, look up a policy, check a claim. A common failure is routing on *topic words* instead of the *action*. Asked to "draft an email", an assistant returns documents that merely contain the word "email". Marsh McLennan described this exact failure as a key weakness of its LenAI assistant ([case study](https://www.rubrik.com/blog/ai/25/how-marsh-mclennan-saved-over-1-million-hours-of-team-time-with-agentic-ai)).

RouteCheck is a routing layer that:

1. **Routes on the action, not the topic.** It finds the first action phrase in the request ("draft", "find", "summarize", "book") and weights it above nouns like *email*, *policy* or *claim*.
2. **Asks instead of guessing.** When there is no action ("claims policy") or confidence is low, it asks one clarifying question offering the two most likely tools.
3. **Logs every decision.** Each request, its tool scores, the action phrase used and the final decision go to a JSONL audit log, so wrong routes can be reviewed and fixed.

## Results

Held-out test set: **100 requests**, made up of 78 with one correct tool (33 of them *lexical traps*) and 22 ambiguous ones where the right move is to ask.

| Router | Clear: correct | Clear: wrong tool | Lexical traps: wrong tool | Clear: asked instead | Ambiguous: asked | Confident-wrong (all) |
|---|---|---|---|---|---|---|
| Keyword similarity (baseline) | 54% | 46% | 64% | 0% | 0% | 58% |
| Intent classifier, always routes | 95% | 5% | 12% | 0% | 0% | 26% |
| **RouteCheck** | **99%** | **0%** | **0%** | 1% | **86%** | **3%** |

- **Wrong-tool rate on clear requests fell from 46% (keyword baseline) to 0% (0 of 78).**
- **86% of ambiguous requests (19 of 22) got a clarifying question** instead of a guess.
- **Confident wrong answers across all 100 requests fell from 58% to 3%.**

*Confident-wrong* counts wrong-tool routes on clear requests plus guesses on ambiguous ones: how often a user would get a confident, wrong answer.

### Examples of the failures it fixes

| Request | Correct | Baseline | RouteCheck |
|---|---|---|---|
| Draft a follow-up mail to the insurer about the pending claim | draft_email | claim_status | draft_email |
| Find the training deck on writing client emails | search_documents | draft_email | search_documents |
| Look up the presentation on employee benefits trends | search_documents | policy_lookup | search_documents |
| Find the PDF guide on filing a reimbursement claim | search_documents | claim_status | search_documents |
| claims policy | *ask* | (always routes) | asks: policy question or claim status? |

### Where it still fails (all 4 test misses)

- *"Where is the email template for claim rejections?"* got a question instead of `search_documents`. The "where is" cue is suppressed when a claim is mentioned (so "where is my claim?" goes to claim status), which also catches this case. The cost is one extra question, not a wrong answer.
- Three ambiguous requests were routed instead of questioned: *"Priya's email about the renewal"* (draft_email), *"Sort out tomorrow's call with Rahul"* (schedule_meeting) and *"policy wording for Acme"* (policy_lookup). Each has no clear action phrase, but the classifier was confident enough to pass the gate.

## How it was evaluated

- **The test set was written first and frozen** (`data/FROZEN.sha256`) before any router code existed. `evaluate.py` refuses to run if it changes.
- **Thresholds were tuned only on a separate 46-request dev set.** Two general rules came from dev errors: a bare noun phrase with no action gets a question, and "get the …" is a search verb.
- **The router code was checksummed before the single test run** (`results/ROUTER_FROZEN_BEFORE_TEST.sha256`).
- Full per-request decisions for all three routers are in `results/test_decisions.jsonl`, and RouteCheck's audit log is in `results/audit_log.jsonl`.

**Limitations, stated plainly:** the dev and test sets are synthetic and hand-written by the same author as the action-phrase rules, so these numbers show the approach works on deliberately tricky phrasing. They are not a measurement on real user traffic. The baseline is keyword (TF-IDF) similarity, not a neural embedding model, because pretrained embeddings could not be downloaded in the build environment. The next step would be evaluating on a sample of real, anonymised assistant requests and swapping in an embedding baseline.

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q                 # 13 tests
python evaluate.py --tune           # tune thresholds on dev
python evaluate.py --final          # one-time evaluation on the held-out test set
python app.py                       # demo at http://localhost:7860
```

Deploy the demo to Render with the included `render.yaml` (start command `python app.py`).

## Layout

```
routecheck/tools.py           the six tools and their descriptions
routecheck/training_data.py   canonical training utterances (separate from eval data)
routecheck/routers.py         KeywordRouter (baseline), ClassifierRouter, RouteCheck
data/build_eval_sets.py       the frozen dev and test sets
evaluate.py                   tuning and held-out evaluation
app.py                        Gradio demo: baseline vs RouteCheck side by side
tests/                        pytest suite
```
