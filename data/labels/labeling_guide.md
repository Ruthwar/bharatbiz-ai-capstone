# Synthetic message label guide

Use the master-plan intents: delivery_complaint, damaged_item, missing_item, product_request, scheme_question, supplier_delay, competitor_observation, other. Record explicit entities only, exact evidence spans, uncertainty, urgency with evidence, source type, language and review label. Do not infer a missing date, quantity, SKU, order reference or identity. Keep held-out evaluation examples separate from prompt-tuning data.

The held-out extraction set is `data/eval/heldout_extraction.jsonl`. It uses `split: held_out`, stable `HOLD-*` IDs, explicit nullable entities and evidence spans that must occur verbatim in `text`. Do not copy its records into `data/synthetic/messages.jsonl` or use it to create prompts, rules or golden retrieval queries.
