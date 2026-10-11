"""The tools an enterprise assistant can route a request to.

Modelled on the kind of tools an internal assistant for an insurance-broking
and employee-benefits business would expose.
"""

TOOLS = {
    "draft_email": "Write, draft, compose or reply to an email or message to someone.",
    "search_documents": "Find, search for or locate existing files, documents, decks, templates or reports in the knowledge base.",
    "policy_lookup": "Answer questions about company HR policies and employee benefits: leave, insurance coverage, eligibility, reimbursement limits, rules.",
    "claim_status": "Check the status, progress or payout of a submitted insurance claim or reimbursement claim.",
    "schedule_meeting": "Book, schedule, reschedule or move meetings, calls and calendar events.",
    "summarize_document": "Summarize, condense or give the key points of a document, transcript, email thread or report the user provides.",
}

TOOL_NAMES = list(TOOLS)

# Human-readable labels used in clarifying questions.
TOOL_LABELS = {
    "draft_email": "draft an email",
    "search_documents": "find a document",
    "policy_lookup": "answer a policy or benefits question",
    "claim_status": "check a claim's status",
    "schedule_meeting": "schedule a meeting",
    "summarize_document": "summarize a document",
}
