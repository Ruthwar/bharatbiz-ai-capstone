# Held-out intent and extraction evaluation set

`heldout_extraction.jsonl` is a synthetic, labelled evaluation-only set. It is kept separate from `data/synthetic/messages.jsonl` and must not be used for prompt tuning, rule tuning, examples, or retrieval-query construction.

Each record contains:

- `message_id`: stable held-out identifier.
- `split`: always `held_out`.
- `source_type`: always `synthetic`.
- `state_version`: the synthetic state used to label the example.
- `text`: the original message.
- `intent`: the expected master-plan intent.
- `entities`: explicit entities only; missing facts remain `null`.
- `evidence_spans`: exact substrings supporting the intent or entity.
- `uncertainty`: facts that are not asserted by the text.

The set is measured after workflow or prompt changes are frozen. Results must be reported separately from any authorized real or pilot data.
