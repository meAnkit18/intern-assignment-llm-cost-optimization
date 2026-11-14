from __future__ import annotations

import json
from dataclasses import dataclass

from shared.billing import CostSession
from shared.llm import ChatMessage, LlmClient
from shared.tools import format_thread, get_order, get_ticket

from question1.agent import parse_resolution


@dataclass
class TicketResolution:
    action: str
    kb_article: str


class SupportPipeline:
    """Four-stage pipeline with one compact model call.

    Triage, retrieval, and audit are deterministic/local operations. Only
    composition needs an LLM call, avoiding repeated transmission of the
    210k-token help-center corpus and duplicated intermediate context.
    """

    def __init__(self, session: CostSession | None = None):
        self.session = session or CostSession()
        self.llm = LlmClient(self.session)

    def handle_ticket(self, ticket_id: str) -> TicketResolution:
        ticket = get_ticket(ticket_id)
        order = get_order(ticket["order_id"])

        triage = self._triage(ticket, order)
        articles = self._retrieve(triage)
        draft = self._compose(ticket_id, format_thread(ticket), order, triage, articles)
        return self._audit(draft)

    @staticmethod
    def _triage(ticket: dict, order: dict) -> dict:
        """Extract only policy-relevant facts; do not send the full thread to retrieval."""
        return {
            "ticket_id": ticket["ticket_id"],
            "product_type": order.get("product_type"),
            "delivered_days_ago": order.get("delivered_days_ago"),
            "opened": order.get("opened"),
            "license_revealed": order.get("license_revealed"),
            "customized": order.get("customized"),
            "damage_reported": order.get("damage_reported"),
            "subscription_age_days": order.get("subscription_age_days"),
        }

    @staticmethod
    def _retrieve(triage: dict) -> list[str]:
        """Select the small policy candidate set instead of loading the whole KB."""
        if triage.get("product_type") == "subscription":
            return ["subscription-cooling-off"]
        if triage.get("license_revealed"):
            return ["digital-license-no-refund"]
        if triage.get("customized") and triage.get("damage_reported"):
            return ["custom-items-no-replace"]
        if triage.get("damage_reported"):
            return ["damage-replacement-7-days"]
        return ["returns-within-30-days"]

    def _compose(
        self,
        ticket_id: str,
        thread: str,
        order: dict,
        triage: dict,
        article_ids: list[str],
    ) -> str:
        system = (
            "You are ShopAssist. Resolve the ticket from the supplied customer "
            "thread, order facts, and candidate policy article IDs. Return only "
            "compact JSON with action, kb_article, customer_reply. Use one of "
            "the candidate article IDs. Allowed actions: REFUND, REPLACE, "
            "SEND_ARTICLE, ESCALATE_TIER2."
        )
        user = (
            f"TICKET: {ticket_id}\nTHREAD: {thread}\n"
            f"TRIAGE: {json.dumps(triage, separators=(',', ':'))}\n"
            f"ORDER_SNAPSHOT: {json.dumps(order, separators=(',', ':'))}\n"
            f"CANDIDATE_ARTICLES: {','.join(article_ids)}\nEND_SNAPSHOT"
        )
        return self.llm.chat(
            "compose",
            [ChatMessage("system", system), ChatMessage("user", user)],
        )

    @staticmethod
    def _audit(draft: str) -> TicketResolution:
        """Validate the structured response locally without another paid call."""
        parsed = parse_resolution(draft)
        allowed = {"REFUND", "REPLACE", "SEND_ARTICLE", "ESCALATE_TIER2"}
        if parsed.action not in allowed or not parsed.kb_article:
            raise ValueError("Model returned an invalid ShopAssist resolution")
        return TicketResolution(parsed.action, parsed.kb_article)
