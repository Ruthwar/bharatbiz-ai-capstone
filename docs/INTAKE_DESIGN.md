# Intake design: message to decision-ready record

**Status:** design accepted for the next slice, 2026-11-09. Supersedes the earlier "receipt only, never ask" position.
**Scope:** academic capstone prototype. Synthetic or authorized data only. No live ERP, WhatsApp, payment or purchasing integration.

This document covers the layer in front of the SCN-003 decision spine: how free-form messages from retailers, suppliers and sales staff become evidence-linked events, and how they reach a human decision. It does not change the arithmetic, ranking or verification described in `SCN-003_DESIGN.md`.

## 1. The boundary

The system may **collect facts**. It may never **make commitments**.

| Allowed | Not allowed |
| --- | --- |
| Acknowledge receipt | Promise a delivery date, quantity, price or credit |
| Ask a question needed to complete the record | Advise the sender, negotiate, or explain a policy decision |
| Record what was said, with the exact words | Treat a sender's claim as confirmed operational state |
| Route to a human with a recommendation | Order, pay, allocate stock, or reply substantively on its own |

Asking "which pack, 1 L pouch or bottle?" is data collection. Saying "we will deliver tomorrow" is a commitment. Only the second is out of scope. Clarification therefore stays inside the system; clarification *replies to the sender* become a human task.

## 2. Three layers

```text
channel adapter  ->  intake (understanding)  ->  routing  ->  decision spine  ->  human review
normalise,            classify, extract,          intent ->      inventory/orders/      approve or
identify, dedup       slot-fill, validate         handler        supplier/cash/          reject, no
                      ask one question             or triage      optimizer/verifier      execution
```

Only the channel adapter is WhatsApp-specific. Replacing the demo chat page with a webhook changes nothing downstream.

## 3. Open-world taxonomy

Eight intents come from the master plan and remain the routing vocabulary. They are **not** a claim that messages are limited to eight kinds.

- Intents are returned as a **list**, not a single label. One message may carry a complaint and a scheme question; that produces two events.
- `other` means "a known intent that needs no automated action". `unclassified` means "not recognised". They must never be merged: unclassified volume is the signal used to grow the taxonomy.
- Unknown intents keep their extracted facts, parties, product, urgency and unknowns. Understanding degrades gracefully; only automation stops.
- The taxonomy is versioned (`taxonomy_version`). Growth path: triage clusters unclassified messages, a human proposes a new intent, slot spec and handler, and it ships as a pull request.

Known families that are not yet in the routing vocabulary: orders, order changes, payments and credit, returns and credit notes, price revision, MOQ change, scheme claims, logistics and partial dispatch, invoice disputes, churn and competitor signals.

## 4. Slots and the question loop

Each intent declares what a decision needs. The system may ask **one** question per turn, for the missing slot with the largest effect on the plan.

```python
class SlotSpec(BaseModel):
    intent: str
    required: list[str]        # must be present, with evidence, before routing
    optional: list[str]        # recorded when stated; never asked for unless decision-relevant
    askable_by: list[str]      # party types allowed to be asked about this slot
    max_rounds: int = 2
```

Rules:

1. **The model never decides completeness.** A deterministic validator checks presence, that `text[start:end] == evidence_span`, and that any SKU exists in the catalogue.
2. **Questions are templates keyed to a slot**, chosen by the slot, not free-form generation. No advice, no estimates, no commitment.
3. **Ask only decision-relevant slots.** If a field cannot change the recommended plan, do not ask for it.
4. **Never ask the wrong party.** A retailer cannot know a supplier's dispatch date.
5. **Hard stop after `max_rounds`.** The item goes to human triage with the transcript.
6. **A reply that introduces a different intent forks a new event.** It is never silently absorbed.

An unanswered or ambiguous message is a valid outcome: it is recorded and triaged, not guessed.

## 5. Acknowledgements

Two kinds, both template-generated, never model-generated.

| Kind | When | Content |
| --- | --- | --- |
| `receipt` | Immediately on receipt | "Received. It will be reviewed." |
| `complete` | Required slots satisfied | "All details noted. It will be processed." |

Rules:

1. Templates per verified sender language. English, Hindi and Hinglish at minimum.
2. An acknowledgement asserts nothing: no date, quantity, price, reference or promise.
3. Duplicates are not acknowledged twice.
4. An acknowledgement means **received**, not **processable**. A state-version mismatch still receives a receipt and the item lands in triage with a processing error.
5. Automated receipt and completion acknowledgements are a deliberate, narrow exception to "no unreviewed retailer-facing messages". All substantive replies require human approval.

## 6. Routing and triage

```python
HANDLERS = {
    "supplier_delay": _process_supplier_delay,
    # delivery_complaint, product_request, scheme_question and the rest
    # are owned by other team members and attach here behind the same interface
}
```

Misses, low confidence, unregistered intents, failed validation and exhausted slot rounds all produce `routed_action: "human_triage"`. Nothing is dropped and nothing is guessed.

The router is the integration seam: module owners add a handler without touching intake code.

## 7. Human intervention and approval expiry

States: `received -> acked -> extracted -> routed -> pending_review | triaged -> approved | rejected`.

- Approve and reject affect the demo record only. No purchase, payment, stock update or outbound message is executed.
- **An approval covers a specific deal, not a product.** If the rate, quantity, arrival date or underlying state changes, the approval is void and returns for review. Nothing is silently re-priced.
- Every decision records what the approver saw: the plan id, the state version, the evidence, and the numeric inputs.

## 8. Known gaps in this slice

- **Mid-delay price change** is not a first-class intent. Prices are read from state at calculation time; there is no price validity window and no automatic invalidation of an in-flight approval. This is the highest-value gap to close next.
- **Partial dispatch** ("60% now, 40% next week") is not modelled; all incoming units for the affected SKU are treated as delayed.
- **Asynchronous channels.** WhatsApp retries and delivers media; the demo is synchronous text with a deduplicated message id.
- **Persistence.** The demo ledger is SQLite (`data/runtime/ledger.sqlite3`, overridable with `BHARATBIZ_LEDGER_DB`) and keeps processed messages, open intakes and the review queue across a restart. `python scripts/reset_demo.py` clears it between demos. A production store would also need migration and retention rules.
- **Identity.** The demo UI selects the sender. Planning now requires a `supplier` account whose `party_id` matches the supplier named in the message; anything else goes to human triage. A real channel would derive the party from the authenticated account and would not let `source_type` be self-declared.
- **Voice notes and images** are out of scope. Evidence spans assume text.

## 9. Evaluation

Reported separately for `rules`, `llm` and hybrid, on the same split:

- Closed-set intent accuracy and macro-F1; multi-intent recall.
- Per-field precision and recall; exact-span match rate.
- Unsupported-assertion rate (must be 0).
- Open-set detection rate: out-of-taxonomy messages must land in `unclassified`, not a wrong known class.
- Triage rate, clarification rounds per intake, human override rate.
- Latency, tokens and cost per resolved intake (not per message).
- Business effect through the unchanged spine: stockout units, late units, unmet units, cash headroom, total cost.

Keep held-out examples out of prompt tuning. Synthetic and real results stay separate.

## 10. Out of scope

Live WhatsApp integration, outbound sending, attachments, authentication beyond the demo, automatic purchasing, payment, pricing, credit decisions, and any unreviewed retailer-facing response.
