"""Builds the frozen evaluation sets (dev.jsonl and test.jsonl).

Written BEFORE any routing code, and never edited after the routers were built.
- dev.jsonl  : used only to tune the clarification thresholds.
- test.jsonl : held out; evaluated once, at the end.

Each clear request has one correct tool. Many are deliberate "lexical traps":
the request contains words that belong to a different tool (e.g. "Write an
email asking for the policy document" mentions policy and document, but the
action is drafting an email). Ambiguous requests have no single right tool;
the correct behaviour is to ask a clarifying question.
"""
import json
from pathlib import Path

AMB = "AMBIGUOUS"

TEST = {
    "draft_email": [
        ("Draft an email to the client about the renewal timeline", False),
        ("Can you write an email to HR asking about my leave balance", True),
        ("Compose a reply to Anita thanking her for the claim documents", True),
        ("Write a polite email declining the meeting on Friday", True),
        ("Help me email the broker that the policy documents are ready", True),
        ("Draft a follow-up mail to the insurer about the pending claim", True),
        ("I need to send an email to the team summarizing today's call", True),
        ("Write to the client explaining why the premium went up", False),
        ("Prepare an email inviting everyone to the benefits webinar", True),
        ("Reply to the underwriter's email and ask for the loss runs", False),
        ("Draft an email", False),
        ("Can you put together a quick email to Vikram asking for the signed document", True),
        ("Email the claimant that we need two more documents to process the claim", True),
        ("Write an out-of-office email for next week", False),
    ],
    "search_documents": [
        ("Find the latest version of the Acme renewal deck", False),
        ("Where is the email template for claim rejections?", True),
        ("Search SharePoint for the 2025 broking market report", False),
        ("Locate the document that lists our approved email signatures", True),
        ("Pull up the slides from last week's client meeting", True),
        ("Show me files about cyber insurance for small businesses", False),
        ("Find the PDF guide on filing a reimbursement claim", True),
        ("Get me the onboarding checklist document", False),
        ("Find the training deck on writing client emails", True),
        ("Where can I find the meeting notes template?", True),
        ("Search for the contract we signed with Zenith Logistics", False),
        ("Find all documents mentioning the Mumbai flood claims", True),
        ("Look up the presentation on employee benefits trends", True),
        ("I'm looking for the SLA document for the claims team", True),
    ],
    "policy_lookup": [
        ("How many days of paternity leave do I get?", False),
        ("Does our group health insurance cover my parents?", False),
        ("What's the policy on working from home?", False),
        ("Am I eligible for the gratuity payout after 4 years?", False),
        ("Is IVF covered under the employee medical plan?", False),
        ("What is the reimbursement limit for internet bills?", False),
        ("Can I carry forward unused annual leave to next year?", False),
        ("What does the travel policy say about business class?", False),
        ("Is there a notice period if I resign during probation?", False),
        ("Does the company match contributions to the provident fund?", False),
        ("What's the dress code policy for client visits?", False),
        ("How much is the maternity benefit under our policy?", False),
        ("Are dental treatments covered by insurance?", False),
        ("Do I need manager approval to expense a client dinner?", False),
    ],
    "claim_status": [
        ("What's the status of my medical claim from last month?", False),
        ("Has claim CLM-48213 been approved yet?", False),
        ("Track the reimbursement I submitted for my hospital bill", False),
        ("Why is my claim still pending?", False),
        ("Check whether the insurer has settled the warehouse fire claim", False),
        ("Did my dental reimbursement go through?", True),
        ("Where is my claim stuck?", False),
        ("Any update on claim number 77120?", False),
        ("Has the payout for my car accident claim been processed?", False),
        ("Is my cashless hospitalization claim approved?", False),
        ("Show the current stage of the Zenith marine claim", False),
        ("When will my submitted claim be paid?", False),
    ],
    "schedule_meeting": [
        ("Book a 30-minute call with the client next Tuesday", False),
        ("Schedule a meeting with Priya and Rahul tomorrow at 3", False),
        ("Set up a review of the renewal document with the team on Friday", True),
        ("Find a slot for a claims review meeting this week", True),
        ("Reschedule my 4 pm meeting to Thursday", False),
        ("Put a 1:1 with my manager on the calendar", False),
        ("Arrange a call with the insurer to discuss the policy terms", True),
        ("Can you organize a benefits Q&A session for the team next month?", True),
        ("Block 2 hours on Wednesday for the email migration workshop", True),
        ("Invite the underwriting team to a sync on Monday", False),
        ("Move the client presentation meeting to next week", True),
        ("Set a meeting to go over the claim backlog", True),
    ],
    "summarize_document": [
        ("Summarize the attached renewal proposal", False),
        ("Give me a TL;DR of this 40-page policy wording", True),
        ("What are the key points in the claims report I just uploaded?", True),
        ("Condense the meeting transcript into five bullets", True),
        ("Summarize this email thread for me", True),
        ("Can you shorten this contract into a one-paragraph overview?", False),
        ("Give me the highlights of the market outlook PDF", False),
        ("Break down the main takeaways from this benefits survey document", True),
        ("Summarize the underwriter's comments in this doc", False),
        ("What does this attached document say, in brief?", False),
        ("Make a short summary of the board meeting minutes", True),
        ("Recap this policy document in plain language", True),
    ],
    AMB: [
        "email",
        "the renewal deck",
        "claims policy",
        "Priya's email about the renewal",
        "Acme meeting",
        "leave",
        "Help with the Zenith claim",
        "insurance",
        "the benefits document",
        "Can you help me with the client email?",
        "meeting notes from Monday",
        "renewal",
        "I need something about dental",
        "client follow-up",
        "Handle the reimbursement",
        "Sort out tomorrow's call with Rahul",
        "the contract",
        "policy wording for Acme",
        "What about my claim and the leave policy?",
        "help",
        "travel",
        "Do the thing for the insurer",
    ],
}

DEV = {
    "draft_email": [
        ("Write an email to Neha confirming the policy start date", True),
        ("Draft a message to the client asking for their claims history", True),
        ("Compose an email to the team about the new document portal", True),
        ("Reply to Arjun and say I can't make the meeting", True),
        ("Send a thank-you email to the insurer", False),
        ("Write a short note to finance about the delayed invoice", False),
    ],
    "search_documents": [
        ("Find the claims escalation matrix document", True),
        ("Where's the policy wording template for marine cover?", True),
        ("Search for last quarter's renewal tracker", False),
        ("Pull up the email etiquette guide", True),
        ("Locate the minutes from the Tuesday meeting", True),
        ("Get the client onboarding deck", False),
    ],
    "policy_lookup": [
        ("How many sick days am I allowed per year?", False),
        ("Is my spouse covered under the health plan?", False),
        ("What's the rule for claiming overtime?", True),
        ("Can I take leave during my notice period?", False),
        ("Does the policy cover maternity for adoptions?", False),
        ("What's the limit on meal expenses when travelling?", False),
    ],
    "claim_status": [
        ("Has my eye surgery claim been settled?", False),
        ("What stage is claim 55021 at?", False),
        ("Is my travel reimbursement still under review?", False),
        ("Check if the Acme property claim was paid", False),
        ("Did the insurer approve my outpatient claim?", False),
        ("Status of my pharmacy reimbursement please", False),
    ],
    "schedule_meeting": [
        ("Schedule a call with the broker on Thursday morning", False),
        ("Book a room for the claims team huddle", True),
        ("Set up a policy walkthrough with the new joiners", True),
        ("Push my 11 am to the afternoon", False),
        ("Add a renewal planning session to everyone's calendar", False),
        ("Arrange a meeting to review the email campaign", True),
    ],
    "summarize_document": [
        ("Summarize the uploaded policy schedule", True),
        ("Key takeaways from this claims audit, please", True),
        ("Shorten this email chain into the main decisions", True),
        ("Give me a summary of the attached meeting notes", True),
        ("TL;DR this renewal proposal", False),
        ("Boil down this 20-page report to three points", False),
    ],
    AMB: [
        "claims",
        "the Acme deck",
        "my leave",
        "the email from the underwriter",
        "Monday's meeting",
        "benefits",
        "the policy document",
        "Rahul",
        "Do something with this renewal",
        "help me with the claim and the email",
    ],
}


def to_rows(spec, prefix):
    rows = []
    i = 0
    for label, items in spec.items():
        for item in items:
            i += 1
            if label == AMB:
                rows.append({"id": f"{prefix}-{i:03d}", "text": item, "label": AMB, "trap": False})
            else:
                text, trap = item
                rows.append({"id": f"{prefix}-{i:03d}", "text": text, "label": label, "trap": trap})
    return rows


def main():
    out = Path(__file__).parent
    for name, spec, prefix in [("test", TEST, "t"), ("dev", DEV, "d")]:
        rows = to_rows(spec, prefix)
        with open(out / f"{name}.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        n_amb = sum(r["label"] == AMB for r in rows)
        n_trap = sum(r["trap"] for r in rows)
        print(f"{name}: {len(rows)} requests ({len(rows) - n_amb} clear, {n_trap} lexical traps, {n_amb} ambiguous)")


if __name__ == "__main__":
    main()
