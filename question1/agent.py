from __future__ import annotations

import json
import re
from dataclasses import dataclass

from shared.billing import CostSession
from shared.llm import ChatMessage, LlmClient
from shared.tools import format_thread, get_order, get_ticket


@dataclass
class TicketResolution:
    action: str
    kb_article: str
    customer_reply: str
    raw_completion: str


def parse_resolution(text: str) -> TicketResolution:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"No JSON in model output:\n{text[:400]}")
    data = json.loads(match.group())
    return TicketResolution(
        action=str(data["action"]).upper(),
        kb_article=str(data["kb_article"]),
        customer_reply=str(data.get("customer_reply", "")),
        raw_completion=text,
    )


class SupportCopilot:
    """Single-call ShopAssist copilot with a compact, policy-focused prompt."""

    def __init__(self, session: CostSession | None = None):
        self.session = session or CostSession()
        self.llm = LlmClient(self.session)

    def build_messages(self, ticket_id: str) -> list[ChatMessage]:
        ticket = get_ticket(ticket_id)
        order = get_order(ticket["order_id"])
        # Keep the customer context and the structured facts; omit the full KB,
        # verbose few-shot traces, random run IDs, and unnecessary order formatting.
        system = (
            "You are ShopAssist. Resolve the ticket using the customer thread and "
            "order facts. Return only compact JSON with action, kb_article, "
            "customer_reply. Allowed actions: REFUND, REPLACE, SEND_ARTICLE, "
            "ESCALATE_TIER2. Cite the exact supporting article ID."
        )
        user = (
            f"TICKET: {ticket_id}\n"
            f"THREAD: {format_thread(ticket)}\n"
            f"ORDER_SNAPSHOT: {json.dumps(order, separators=(',', ':'))}\n"
            "END_SNAPSHOT"
        )
        return [ChatMessage("system", system), ChatMessage("user", user)]

    def handle_ticket(self, ticket_id: str) -> TicketResolution:
        completion = self.llm.chat("handle_ticket", self.build_messages(ticket_id))
        return parse_resolution(completion)
