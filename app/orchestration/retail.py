import hashlib
import re
from datetime import timedelta

from app.agents.market import group_themes
from app.agents.retailer import RECURRING_WINDOW_DAYS, follow_up_priority
from app.extraction.retail_intents import RETAIL_SOURCES
from app.orchestration.drafts import build_draft
from app.schemas.contracts import BusinessState, MessageSubmission
from app.schemas.retail import CaseProposal, MarketObservation, ResponseDraft

COMPLAINTS = {"delivery_complaint", "damaged_item", "missing_item"}
GROUP_FIELDS = ("signal_type", "subject", "competitor_name", "product_label", "offer", "area")


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _known_retailer(state: BusinessState, retailer_id: str | None) -> str | None:
    if retailer_id and any(row["retailer_id"] == retailer_id for row in state.retailers):
        return retailer_id
    return None


def _product_label(state: BusinessState, sku_id: str | None) -> str | None:
    row = next((row for row in state.products if row["sku_id"] == sku_id), None)
    return f"{row['product_name']} {row['pack_description']}" if row else None


def _offer(text: str) -> str:
    found = re.search(r"\b\d+(?:\.\d+)?\s*(?:percent|%)\s*off\b|\bbuy\b[^.?!]{0,40}\bget\b[^.?!]{0,40}", text, re.I)
    return found.group(0).strip() if found else text.strip()


def _observation(
    message: MessageSubmission,
    result: dict,
    state: BusinessState,
) -> MarketObservation | None:
    context = result.get("market_context")
    if not context:
        return None
    event = result["event"]
    competitor = context.get("signal_type") == "competitor_observation"
    sender = message.sender
    sku_id = context.get("matched_sku_id") or event.get("inferences", {}).get("catalogue_sku_id")
    product_label = context.get("requested_product_label") or _product_label(state, sku_id)
    if not product_label:
        product_fact = next(
            (fact for fact in event.get("extracted_facts", []) if fact.get("field") == "product"), None
        )
        product_label = (product_fact or {}).get("value") or "unknown"
    competitor_name = "unknown"
    area = "unknown"
    if competitor:
        found = re.search(r"\bcompetitor\s+(.+?)\s+(?:is|has|was|offers?|offering)\b", message.text, re.I)
        competitor_name = found.group(1).strip() if found else "unknown"
        area_match = re.search(r"\bin\s+([A-Za-z][A-Za-z ]{1,50}?)(?:[.,;!?]|$)", message.text)
        area = area_match.group(1).strip() if area_match else "unknown"
    retailer_id = sender.party_id if sender and sender.party_type == "retailer" else None
    return MarketObservation(
        observation_id=_stable_id("obs", event["event_id"]),
        event_id=event["event_id"],
        signal_type="competitor_observation" if competitor else "pack_size_request",
        subject=competitor_name if competitor else product_label,
        sku_id=sku_id,
        competitor_name=competitor_name,
        product_label=product_label,
        offer=_offer(message.text) if competitor else "",
        area=area,
        retailer_id=retailer_id,
        reporter_id=sender.party_id if sender else None,
        observed_at=message.observed_at.isoformat(),
        observation_text=message.text,
        evidence_span=message.text,
        source_message_id=message.message_id,
    )


def _records(
    message: MessageSubmission,
    result: dict,
    state: BusinessState,
    store,
) -> tuple[dict | None, CaseProposal | None, ResponseDraft | None, list[MarketObservation]]:
    event = result["event"]
    sender = message.sender
    retailer_id = _known_retailer(
        state,
        sender.party_id if sender and sender.party_type == "retailer" else None,
    )
    interaction = None
    if message.source_type in RETAIL_SOURCES:
        interaction = {
            "event_id": event["event_id"],
            "message_id": message.message_id,
            "retailer_id": retailer_id,
            "intent": event["event_type"],
            "reporter_id": sender.party_id if sender else None,
            "observed_at": message.observed_at.isoformat(),
        }

    case = None
    draft = None
    case_context = result.get("case_context")
    if case_context and not case_context.get("clarification_slot"):
        retailer_id = _known_retailer(state, case_context.get("retailer_id"))
        if retailer_id:
            sku_id = case_context.get("sku_id")
            since = (message.observed_at - timedelta(days=RECURRING_WINDOW_DAYS)).isoformat()
            prior = [
                row
                for row in store.interactions_for(retailer_id, since)
                if row["intent"] == event["event_type"]
            ]
            priority, reasons = follow_up_priority(
                state, retailer_id, event["event_type"], message.text, sku_id, len(prior)
            )
            orders = case_context.get("matched_orders") or []
            case = CaseProposal(
                case_id=_stable_id("case", event["event_id"]),
                retailer_id=retailer_id,
                category=event["event_type"],
                priority=priority,
                priority_reasons=reasons,
                sku_id=sku_id,
                order_ids=[row["order_id"] for row in orders],
                summary=result["recommendation"]["summary"],
                follow_up="Verify delivery evidence and record a staff resolution before closing the case.",
            )
            draft = build_draft(
                event["event_id"],
                retailer_id,
                "complaint_ack",
                message.language,
                category=event["event_type"],
                product_label=_product_label(state, sku_id),
                order_id=orders[0]["order_id"] if len(orders) == 1 else None,
            )
    elif result.get("market_context", {}).get("signal_type") == "smaller_pack_request" and retailer_id:
        context = result["market_context"]
        draft = build_draft(
            event["event_id"],
            retailer_id,
            "request_ack",
            message.language,
            product_label=context.get("requested_product_label"),
        )

    observation = _observation(message, result, state)
    return interaction, case, draft, [observation] if observation else []


def _same_group(row: dict, observation: MarketObservation) -> bool:
    expected = observation.model_dump()
    return all((row.get(field) or "") == (expected.get(field) or "") for field in GROUP_FIELDS)


def _refresh_market_context(result: dict, observations: list[MarketObservation], store) -> None:
    if not observations:
        return
    current = observations[0]
    rows = [row for row in store.observations() if _same_group(row, current)]
    theme = next(
        (
            row
            for row in group_themes(rows)
            if all(getattr(row, field) == getattr(current, field) for field in GROUP_FIELDS)
        ),
        None,
    )
    if theme is None:
        return
    context = result["market_context"]
    if current.signal_type == "competitor_observation":
        context["unique_observation_count"] = theme.report_count
        context["distinct_reporter_count"] = theme.distinct_reporters
        context["corroboration"] = theme.label
        context["observations"] = rows
        result["recommendation"]["summary"] = (
            f"Reported competitor signal: {theme.report_count} unique reports from "
            f"{theme.distinct_reporters} distinct reporters; {theme.label.replace('_', ' ')}. "
            "Review evidence only; no competitive action is recommended automatically."
        )
    else:
        context["distinct_retailer_count"] = theme.distinct_reporters
        context["reported_request_count"] = theme.report_count
        context["requests"] = rows
        availability = (
            f"Existing catalogue match: {context['matched_sku_id']}."
            if context.get("catalogue_match")
            else "No existing catalogue pack match was found."
        )
        result["recommendation"]["summary"] = (
            f"Reported pack request from {theme.distinct_reporters} retailers with "
            f"{theme.report_count} reported requests. {availability} Aggregate and verify demand; "
            "do not infer supplier availability or change assortment automatically."
        )


def persist_retail(message: MessageSubmission, result: dict, state: BusinessState, store) -> dict | None:
    if message.source_type not in RETAIL_SOURCES:
        return None
    interaction, case, draft, observations = _records(message, result, state, store)
    if interaction is None and not observations:
        return None
    case_id = store.persist(interaction, case, draft, observations)
    context = {
        "case_id": case_id,
        "draft_id": draft.draft_id if draft else None,
        "observation_ids": [row.observation_id for row in observations],
        "reply_requires_approval": draft is not None,
        "sent_automatically": False,
    }
    result["retail_context"] = context
    if case_id and result.get("case_context"):
        result["case_context"]["case_id"] = case_id
        result["case_context"]["priority"] = case.priority
        result["case_context"]["priority_reasons"] = case.priority_reasons
    _refresh_market_context(result, observations, store)
    return context
