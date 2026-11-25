# 15-minute presentation script

BharatBiz Operations Console. Screen cues in `[brackets]`; spoken lines follow. Numbers match
`docs/PRESENTATION_RUNBOOK.md` and the console.

---

## 0:00 — Opening (1 minute)

`[Overview open. Stand beside the five metric cards.]`

> This is the BharatBiz operations console. A distributor receives operational messages all day —
> a supplier delay, a retailer claim, a recall notice, a dispatch constraint — and every one has
> to become a decision someone can defend.
>
> The console takes that message, extracts the facts with evidence, builds candidate plans,
> verifies them independently, and stops at a human review.
>
> Right now: thirty open order lines, three demand gaps, five decisions waiting for a person,
> two lakh fifty thousand rupees of cash, and two lakh of that deployable above the fifty
> thousand buffer.
>
> Fifteen scenarios are modelled in four groups: core operations, constraints and disruption,
> retail case review, and market and quality signals. The evaluation set is eighty frozen cases
> across seven groups. Everything I show you is running live against the API.

## 1:00 — Scope, control flow and safeguards (1 minute)

`[Scroll to "Controlled decision flow".]`

> The scope first. Core operations: normal day, demand spike, supplier delay, dispatch.
> Constraints: limited cash, stock discrepancy, combined disruption, short-dated stock. Retail:
> complaint, overdue retailer, scheme claim, short-and-damaged. Signals: competitor observation,
> smaller-pack request, batch recall. All fifteen share one contract — evidence, deterministic
> numbers, verified plans, human decision. Five are opened live; the coverage slide maps all fifteen.
>
> The flow is five stages. Channel intake, evidence extraction, candidate planning, independent
> verification, human decision.
>
> Two safeguards sit behind it. Extraction must pass deterministic checks before anything
> downstream sees it: every fact carries a verbatim span, the SKU must exist in the catalogue,
> supplier and retailer IDs must be known, and day counts must be valid. Verification then
> rebuilds the plan from the source numbers; it does not trust the model's arithmetic or summary.
>
> So the model can propose. Deterministic code decides whether the proposal is usable.

## 2:00 — SCN-003, two decision policies (2 minutes)

`[Scenario lab → Scenario: SCN-003 · Supplier delay. Sidebar mode: Deterministic.]`

> A supplier reports a two-day delay on cooking oil. Sixty-two units on hand, fifty-six usable
> after reserve, one hundred and two units of open demand, so forty-six units have to be bought.
>
> `[Press "Run selected scenario".]`
>
> Deterministic mode buys forty-six litres from Balaji Wholesale Distributors at four thousand
> eight hundred seventy-six rupees forty-six paise, arriving on the twenty-fifth. All one
> hundred and two units are fulfilled, none unfilled, twenty-eight arrive late.
>
> The ranking is fixed and stated: fewest unfilled, then fewest late, then earliest arrival, then
> lowest cost. There are no citations in this mode, because the policy passages are context, not
> a ranking input.

`[Switch sidebar mode to Policy-grounded LLM. Press "Run selected scenario" again.]`

> Same evidence, different decision policy. Grounded mode buys from Sri Venkateswara FMCG
> Supply at four thousand three hundred forty-two rupees eighty-six paise, arriving one day
> later. Same fulfilment: one hundred and two of one hundred and two, twenty-eight late.
>
> It states its priority — cost — and the projected headroom above the buffer: one lakh
> ninety-five thousand six hundred fifty-seven rupees.
>
> It also states the trade-off. Balaji costs five hundred thirty-three rupees sixty more, and
> arrives one day earlier. The plan cites three policy passages: costing, delay handling and cash
> control.
>
> Deterministic is not policy-free. It is a fixed policy. Grounded mode can trade a day of
> arrival against five hundred thirty-three rupees, using cited rules, and it shows the trade-off
> instead of hiding it. Both plans end pending review.

## 4:00 — SCN-010, credit exposure (1 minute)

`[Scenario: SCN-010 · Overdue retailer with new order. Mode: Policy-grounded LLM. Run.]`

> Retailer RET-016 already owes fifty-seven thousand four hundred forty-eight rupees past due.
> The new order is thirty kilograms, worth four thousand six hundred twenty rupees. That takes
> exposure to sixty-two thousand sixty-eight rupees against a fifty thousand limit.
>
> The recommendation is to hold the new order for a human credit decision. It cites the
> liquidity and service-continuity policies.
>
> No order is accepted. No credit decision is executed. Nothing is sent to the retailer.

## 5:00 — SCN-011, scheme claim (40 seconds)

`[Scenario: SCN-011 · Scheme claim mismatch. Mode: Deterministic. Run.]`

> A retailer claims ten percent off thirty units. The approved scheme is seven point five
> percent with a forty-unit minimum.
>
> The console does not stretch the scheme to fit the claim. It shows the gap, routes the case to
> scheme-claim review, and waits. This case produces no operational plan, so the decision-mode
> selector correctly does not apply.

## 5:40 — SCN-013, batch recall (1 minute)

`[Scenario: SCN-013 · Batch recall and quality hold. Mode: Policy-grounded LLM. Run.]`

> Recall RCL-001 covers batch BATCH-004: three hundred pieces of SKU-005. One hundred ten
> unreserved pieces can be held immediately, and four open orders use the SKU.
>
> The recommendation is to quarantine the batch. Release is infeasible while the recall requires
> the batch held. It cites the stock-control policy.
>
> The recall path protects stock first. It never re-allocates a recalled batch to an open order.

## 6:40 — SCN-015, dispatch capacity (40 seconds)

`[Scenario: SCN-015 · Dispatch under vehicle capacity. Mode: Deterministic. Run.]`

> Route RTE-001, van AP-09: forty units of capacity against forty-seven units of demand across
> three orders. Seven load plans are feasible; none ships all forty-seven units.
>
> The selected plan loads ORD-0001 and ORD-0018: twenty-six units, one order deferred, zero
> promise risk. The grounded mode reaches the same load and cites the service policy.
>
> The console does not promise what the van cannot carry.

## 7:20 — Intake and the review gate (1 minute)

`[Inbox → expand "Example messages" → "Load editable example" → submit.]`

> This is the intake path. The sender is visible, the message is editable, and the response is
> structured rather than conversational.
>
> Every extracted fact points at the exact words in the message. When a required slot is missing,
> the console asks one clarification question instead of guessing.
>
> The safety block is advisory: prompt-injection signals and PII signals are counted, but they do
> not silently change routing.
>
> The message lands in the review queue. Approving or rejecting is a person's action, and it
> changes review state only. The message body is not stored in traces, and identifiers are masked
> before any external model call.

## 8:20 — Agent runtime (1 minute 30 seconds)

`[Terminal.]`

> The agent layer is a bounded, read-only review loop. Seven tools, all read-only. A planner, an
> executor and a critic.
>
> `[Run: python scripts/agent_review.py --intent supplier_delay --sku-id SKU-003 --supplier-id SUP-005 --delay-days 2]`
>
> Five of a permitted ten tool calls, twelve hundred eighty-eight estimated tokens, about three
> hundred milliseconds, and three citations in force — including the delay-handling policy. No
> failure labels.
>
> The budgets are hard: ten calls, twelve thousand estimated tokens, five seconds. Token counts
> are a characters-over-four estimate, not provider billing.
>
> `[Run the same command with --plan docs/fixtures/malformed_agent_plan.json]`
>
> Here is a malformed plan that names an unsupported tool, approve_order. The validator rejects
> it, labels it unknown_tool, and falls back to the deterministic plan. All five safe steps still
> execute. The unsupported tool never runs.

`[Track B evidence → Agent runtime → "Ask a follow-up without repeating the identifiers".]`

> The follow-up repeats none of the identifiers. The session store resolves intent, SKU, supplier
> and delay from the previous turn. Status is ok, side effects false.
>
> That is persistent state, labelled failure handling, and a hard step cap — the agentic layer
> graded in the brief.

## 9:50 — Evaluation evidence (2 minutes 30 seconds)

`[Track B evidence → Gold set.]`

> The gold set is eighty cases, frozen before the agent layer, written across seven groups:
> canonical scenarios, intent variants, restatements, multi-turn, inbound persistence, authority
> and security, and edge cases.
>
> Result: eighty of eighty. Every group at one hundred percent. Zero failure labels. Median
> latency stays under four hundred milliseconds and the ninety-fifth percentile under six hundred
> thirty, varying with machine load. Every case also checks that no autonomous action was taken.

`[Retrieval upgrades.]`

> Retrieval runs over five hundred thirteen documents and twenty-six hundred three sections,
> with forty frozen queries and twelve strategies across three chunkings.
>
> Base section BM25 gets recall-at-three of one hundred percent, precision-at-one of seventy-seven
> point five, MRR zero point eight five one.
>
> On the larger corpus, reranking lifts precision-at-one from fifty-two point five to sixty-seven
> point five, and recall-at-three from eighty to eighty-five. Paragraph chunking recovers
> ninety-seven point five percent recall-at-three. That is the chunking and reranking evidence.

`[Prompting strategies.]`

> Twelve held-out messages, five strategies: rules, zero-shot, few-shot, and each model prompt
> with one validation-guided repair round.
>
> Few-shot takes stated-entity accuracy from thirty-four point eight to fifty-six point five
> percent, and exact records from zero of twelve to four of twelve. It costs about forty percent
> more tokens: ten thousand ninety-five to about fourteen thousand one hundred.
>
> Few-shot validates on all twelve messages. Zero-shot repair attempted two recoveries and
> recovered none, so the report shows the extra tokens with no accuracy gain.

`[Agent runtime tab, 17-task table.]`

> The agent evaluation is seventeen tasks across seventeen intents. Seventeen complete, four
> point four seven average tool calls, one thousand sixty estimated tokens per task, median
> around a quarter of a second and ninety-fifth percentile inside half a second through the API.
> Zero exceptions, zero failure labels.

## 12:20 — Observability and safety (1 minute 10 seconds)

`[LLM observability.]`

> Every model call, retrieval call and tool call writes a local span. The counters on screen are
> live: several thousand spans, more than four hundred model generations, thousands of retrieval
> calls, hundreds of tool calls and hundreds of thousands of recorded tokens. Span latency sits
> around two point three seconds at the median and five point one at the ninety-fifth percentile.
>
> Open any trace and you can follow extraction, retrieval, planning and review in sequence.

`[Track B evidence → Safety controls.]`

> The read cache returns a miss on the first status call and a hit on the second.
>
> The corpus audit examined two hundred three sections and flagged six policy phrasings — five
> mentioning autonomous action, one mentioning review bypass. These are ordinary policy and SOP
> sentences that the detector matches. A flag never changes routing, approval or a plan.
>
> The PII preview masks seven identifier types. The injection preview is advisory: it reports
> counts and does not alter the decision path.
>
> Limits are enforced rather than described: five-second cache, six hundred requests per minute,
> burst two hundred.

## 13:30 — Architecture and responsible AI (50 seconds)

`[Stay on Safety controls; point at the header.]`

> The console is a Streamlit front end over a FastAPI service, with SQLite stores for business
> state, reviews, agent sessions and traces.
>
> Container definitions pin Python three point twelve, run as a non-root user, copy only what
> they need, and contain no credentials.
>
> Every recommendation is advisory. Approval changes review state only. The system does not
> purchase, pay, reprice, allocate stock or send a message.
>
> That boundary is stated on every evidence tab and enforced in the code: read-only, no business
> actions, human approval required.

## 14:20 — Close (40 seconds)

`[Return to Overview or Decision desk. Point at a review card footer.]`

> "No purchases, payments, stock mutations, outbound messages."
>
> Intake is automated. Evidence is verified. Plans are compared. The decision stays with a
> person.
>
> Every scenario in this walkthrough ended pending review. The human gate is the product, not a
> checkpoint bolted on at the end.
>
> Ask me about any number on the screen, and I will open the case behind it.

---

## If you are running behind

Cut in this order: SCN-011 (40 s), then SCN-015 (40 s), then the retrieval chunking detail (30 s).
Never cut the gold-set result, the agent failure path, or the review gate.

## If a question goes deeper than the screen

| Question | Open |
| --- | --- |
| "Show me the failing case" | Gold set → per-case table; expected versus actual |
| "Show me the sources" | Knowledge → document, section, effective date and licence |
| "Show me the trace" | LLM observability → trace detail |
| "Show me the policy text" | Decision desk → Policy basis |
| "Show me the agent plan" | Agent runtime → steps and observations |

## Numbers you may be asked to repeat

- Gold set: 80/80, seven groups at 100%, p50 184–399 ms, p95 283–625 ms across recorded runs.
- Retrieval: 513 documents, 2,603 sections, 40 queries, 12 strategies; base recall@3 100%,
  reranked expanded-corpus precision@1 67.5%.
- Prompting: 12 messages, 5 strategies; few-shot entities 56.5%, exact 4/12, about 14,100
  tokens (+40%).
- Agent: 17/17 tasks, 4.47 calls, 1,060 tokens, p50 250–422 ms, p95 297–500 ms across recorded
  runs; CLI 5 calls, 1,288 tokens, 3 citations.
- Traces: live counters, several thousand spans, 400+ generations, thousands of retrieval calls;
  span latency around p50 2.3 s, p95 5.1 s.
- Safety: 203 sections audited, 6 flagged; 7 PII types; 600 requests/min, burst 200; 5 s cache.
