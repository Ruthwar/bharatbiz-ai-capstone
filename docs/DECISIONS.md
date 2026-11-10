# Team decision log

Record date, decision, options considered, owner and follow-up issue. Master plan section 21.2 lists kickoff decisions still to confirm.

| Date | Decision / open question | Owner | Due | Status |
|---|---|---|---|---|
| 2026-11-05 | Select primary supplier-delay demo and secondary text-intelligence scenario | Ruthwar + team | Kickoff | Open |
| 2026-11-05 | Confirm GitHub owner/org, visibility and member access | Ruthwar | Kickoff | Open |
| 2026-11-05 | Confirm SQLite for demo and OR-Tools baseline | Ruthwar + Ranjith | Kickoff | Open |
| 2026-11-05 | Confirm model provider; retain no-key mock mode | Ruthwar | Kickoff | Open |
| 2026-11-05 | Confirm simulation-only or permissioned pilot approach | Varsha + team | Kickoff | Open |
| 2026-11-05 | Freeze shared contracts and synthetic dataset import schema | All owners | 2026-11-06 | Open |
| 2026-11-06 | Use the canonical SCN-003 Cooking oil supplier-delay fixture for the first vertical slice | Ruthwar + module owners | Primary demo | Decided for first demo |
| 2026-11-06 | Use deterministic candidate ranking/FIFO before adding OR-Tools; retain no-key mock mode | Ruthwar + Ranjith | Primary demo | Decided for first demo |
| 2026-11-06 | Treat all SKU-003 incoming units as delayed scenario assumptions, not source-extracted facts; preserve unknown revised date and PO reference | Ruthwar + Varsha | Primary demo | Decided for first demo |
| 2026-11-06 | Represent all monetary values as exact `Decimal` rupees with two decimal places across data, contracts, calculations, API output and dashboard display | Ruthwar + Ranjith | Primary demo | Decided for first demo |
| 2026-11-09 | Intake may ask data-completeness questions; it may never make commitments, advise, or reply substantively to a retailer or supplier. Receipt and completion acknowledgements are the only automated outbound text | Ruthwar | Next slice | Decided |
| 2026-11-09 | Intent classification returns a list; `other` (known, no automated action) and `unclassified` (not recognised) stay distinct; unknown intents keep their extracted facts and go to human triage | Ruthwar + Varsha | Next slice | Decided |
| 2026-11-09 | Slot-filling is capped at two question rounds per intake; only decision-relevant slots may be asked, and only of the party that can know them | Ruthwar + module owners | Next slice | Decided |
| 2026-11-09 | An approval covers a specific deal; if rate, quantity, arrival date or underlying state changes, the approval is void and returns for human review | Ruthwar + Ranjith | Next slice | Decided |
| 2026-11-09 | Mid-delay price change, price validity windows and approval invalidation are recorded as a known gap to close before any pilot | Ruthwar + Rohit | Before pilot | Open |
| 2026-11-09 | Model provider and endpoint detail from IIT still pending; no-key rules mode remains the default and the test path | Ruthwar | Next slice | Open |
