# BharatBiz Operations — walkthrough video script

**Version 6** — presenter voice replaced with a natural-pitch neural voice; every segment regenerated and the cut rebuilt to the new sentence timings.
Target runtime: **11 min 11 s** (11:10.86)
Canvas: 1600 × 900, 30 fps, H.264 + AAC
Narration: `en-US-AndrewMultilingualNeural` at natural pitch (+0 Hz), rates +0% to +10%; per-segment values in the modulation table. No artificial pitch lowering. The overview and each scenario are generated as sentence groups and cut to those group boundaries.
Visual language: live workspace only; title and closing cards are the only non-application frames
Master: `tmp/video/final/bharatbiz-walkthrough-v6.mp4`

Workspace data is as of **23 November 2026**; the frozen evaluation run completed on **24 November 2026**.

---

## Timeline

| # | Segment | In | Out | Length | Screen |
|---|---|---|---|---|---|
| 00 | Title card | 00:00 | 00:15 | 0:15 | Animated brand card |
| 01 | Control room, first look | 00:15 | 00:26 | 0:12 | Overview, metric row, tile-by-tile highlight |
| 02 | Control room, explained | 00:26 | 01:40 | 1:14 | Overview metrics, cash, watchlist, orders, flow |
| 03 | Live intake, retailer clarification | 01:40 | 02:25 | 0:44 | Inbox, typed conversation + processing |
| 04 | Decision desk | 02:25 | 02:52 | 0:28 | Review queue and card |
| 05 | SCN-003 supplier delay | 02:52 | 03:50 | 0:57 | Scenario lab, deterministic run |
| 06 | SCN-010 credit review | 03:50 | 04:45 | 0:55 | Scenario lab, policy-grounded result |
| 07 | SCN-013 batch recall | 04:45 | 05:29 | 0:44 | Scenario lab, policy-grounded result |
| 08 | SCN-015 route delivery, load options | 05:29 | 06:22 | 0:53 | Scenario lab, policy-grounded result + options |
| 09 | Evaluation workspace | 06:22 | 07:05 | 0:43 | RAG + extraction results |
| 10 | Gold set | 07:05 | 07:29 | 0:24 | Track B → Gold set |
| 11 | Retrieval upgrades | 07:29 | 08:16 | 0:47 | Track B → Retrieval upgrades |
| 12 | Prompting strategies | 08:16 | 08:39 | 0:23 | Track B → Prompting strategies |
| 13 | Agent runtime | 08:39 | 09:23 | 0:43 | Track B → Agent runtime |
| 14 | Safety controls | 09:23 | 09:55 | 0:32 | Track B → Safety controls |
| 15 | Observability | 09:55 | 10:29 | 0:34 | LLM observability |
| 16 | Knowledge base | 10:29 | 10:53 | 0:25 | Knowledge header + policy state |
| 17 | Closing card | 10:53 | 11:11 | 0:18 | Animated close |

The on-screen chapter pill numbers are **01 Control room, 02 Live intake, 03 Human decision, 04 Supplier delay, 05 Credit review, 06 Batch recall, 07 Route delivery · load options, 08 Evaluation, 09 Gold set, 10 Retrieval, 11 Prompting, 12 Agent runtime, 13 Safety controls, 14 Observability, 15 Knowledge**. These pills are not the timeline row numbers: the opening shot and the explained overview are both part of pill 01.

Each scenario is cut at its result reveal: the setup shot runs until the narration stops describing the situation, and the result shot starts on the sentence that states the numbers. The overview is cut at five narration-group boundaries, so each scroll happens as its sentence begins.

---

## Where the model is used

| Step | Who does it | Model involved |
|---|---|---|
| Channel intake | Application parses sender, conversation and message | No |
| Evidence extraction | Model proposes intent and fields with exact source spans; validator accepts or rejects; deterministic rules are the fallback | **Yes** |
| Candidate planning | Application computes quantities, cost, stock, capacity and cash | No |
| Option selection, policy-grounded mode | Application precomputes every eligible option; model chooses one and cites policy; application rechecks the citation, licence, effective date and arithmetic | **Yes** |
| Independent verification | Application recomputes the numbers; does not call the planner | No |
| Human decision | Reviewer approves, rejects or edits; ledger only | No |
| Agent planning | Rules planner over seven read-only tools | No |

The model never computes stock, cash or capacity, never sets a policy date, never verifies its own selection and never approves. That boundary is stated on screen in the control-room segment.

---

## 00 — Title card (0:15)

**Visual.** Deep navy gradient. Small mark `BB`, wordmark **BharatBiz Operations**, eyebrow **FMCG DISTRIBUTION OPERATIONS**, headline **Evidence in. Decision out.**, subtitle *Inventory, credit and quality decisions — with a person in control*. Thin blue rule animates in. No product UI.

**Narration.**
Every operational decision begins with a message. BharatBiz is an operations console for FMCG distributors. It turns each message into a controlled, evidence-backed decision a person can defend.

**Voice.** rate +0%, natural pitch. Warm and deliberate, but not slow; one short beat between sentences.

---

## 01 — Control room, first look (0:12)

**Visual.** Cut to Overview at the top, already in **Policy-grounded LLM** mode. Hold the header and the five metric cards: 30 open order lines, 8 high priority, 7 pending review, ₹2,50,000 cash, ₹2,00,000 deployable. The tiles light one by one, left to right.

**Narration.**
Behind every message sits a business state: orders, stock, cash and the decisions waiting for a person. The console puts that state on one screen, so the team can see the day before it acts.

**Voice.** rate +6%, natural pitch. Warm, explanatory. No numbers yet; they arrive in the next segment.

---

## 02 — Control room, explained (1:14)

**Visual.** Five beats, each cut to its narration group:
1. Title and metric row; highlight the KPI cards. *(0:00–0:22)*
2. Scroll to **Needs attention** and **Cash protection**; highlight the buffer meter. *(0:22–0:31)*
3. Scroll to **Inventory watchlist**. *(0:31–0:39)*
4. Scroll to **Next orders due**. *(0:39–0:45)*
5. Scroll to **Controlled decision flow**; highlight the five stages; hold on the model-boundary note. *(0:45–1:14)*

**Narration.**
This is the home screen the distributor's operations team opens each morning: today's workload, the cash position, and every signal that needs a decision. Across the top: thirty open order lines, eight high priority, three products short. Cash on hand is two lakh fifty thousand rupees; with a fifty-thousand-rupee floor protected, two lakh is deployable.

Needs attention lists what is already slipping. Cash protection shows the buffer: a plan that drops below the floor is infeasible, however cheap it looks.

The inventory watchlist compares demand with stock, and flags cooking oil in one-litre and five-litre packs, and biscuits, as short.

Next orders due keeps the order book together: retailer, product, quantity and promised date.

Every case then follows one controlled flow: channel intake, evidence extraction, candidate planning, independent verification, and a human decision. The model is used in two steps only: reading a message into evidence, and choosing among verified options in policy-grounded mode. It never calculates stock, cash or capacity, never changes a policy date, and never approves. Everything else is deterministic, so every number can be rechecked.

**Voice.** rate +8%, natural pitch. The first beat is an introduction to the page, not a recital: settle on “home screen”, then the numbers. Slow slightly on “however cheap it looks”. Land “never approves” and “rechecked”.

---

## 03 — Live intake, retailer clarification (0:44)

**Visual.**
1. Open **Inbox**. Set **Recommendation mode** to **Policy-grounded LLM**.
2. Sender: type `Sneha` and select **Sneha General Store · retailer · RET-016**. Conversation ID: `retail-016-delivery`.
3. Type the first message in the chat box, incomplete on purpose: *“Our delivery is late and nothing has arrived. Can you check?”* Click **Send for processing**.
4. Hold the system question **“Which product and pack?”** in the conversation.
5. Reply: *“It is the Tea 1 kg pack.”* Send again.
6. Hold **Latest processing**: route `delivery_complaint_planning`, one clarification round, the extracted **product** row with its evidence, the explicit-unknowns note, and the recommendation naming **ORD-0024**.
7. Return to the full two-turn conversation and hold it.

**Narration.**
Retailer side: the message says the delivery is late and nothing has arrived; no product, no order, no date. Supplier side: the dispatch record is not matched, so the system invents nothing. This is a live model call: it extracts the fields, and every value must point to the words that produced it. It asks one question: which product and pack? The retailer answers: tea, the one kilogram pack.

The product resolves to a catalogue record, and one open order matches: ORD-0024. The route is delivery complaint planning. Every other field stays an explicit unknown. The recommendation asks for delivery evidence and needs human approval before any response or action.

**Voice.** rate +8%, natural pitch. Conversational. Beat before “It asks one question”. Land “live model call” and “human approval”.

---

## 04 — Decision desk (0:28)

**Visual.**
1. Open **Decision desk**. Hold the queue and the selected card.
2. Show **What this means**, then the metric row.
3. Click **Evidence & unknowns**, then **Policy basis**.
4. End on the reviewer decision block; do not click approve or reject.

**Narration.**
Decision desk. The queue is oldest first, and every card has the same structure: what it means, how it was reached, the plan metrics, every alternative, the evidence, the policy basis and the order allocation. Approval changes the review ledger only; it creates no purchase order, moves no stock, releases no payment and sends no message. Rejection is recorded the same way. The machine can prepare a decision, but it cannot execute one.

**Voice.** rate +8%, natural pitch. Even spacing through the list. Land “cannot execute one”.

---

## 05 — SCN-003 supplier delay (0:57)

**Visual.**
1. Click **Scenario lab**. Recommendation mode stays **Deterministic**. Select `SCN-003 · Supplier delay`. Uncheck **Persist the outcome in the SQLite review queue**.
2. Click **Run selected scenario**. Keep 3–4 s of spinner, then jump-cut the remainder of the wait.
3. Result: hold the badges and **What this means**.
4. Scroll to **How the decision was reached**; highlight the independent verification step.
5. Open **Decision** and scroll to **Compare the options**: the selected Balaji row against the two cheaper, later options, with cost, arrival, late units, unfilled and cash left.
6. Continue to **What the extra money buys**; then return to top and hold the pending-review badge.

**Narration.**
Supplier delay. This is the one case we run in deterministic mode, to show the calculation path without a model. Retailer side: several open orders need cooking oil, some already promised. Supplier side: the stock file shows limited free stock, with more arriving later.

Six open orders need one hundred and two litres; fifty-six are free from stock now. The planner weighs suppliers, lead times and cash, then selects Balaji for forty-six litres at four thousand eight hundred and seventy-six rupees, arriving on the twenty-fifth of November. Coverage is complete: one hundred and two litres; twenty-eight arrive late, nothing is unfilled, and one lakh ninety-five thousand rupees remain above the cash floor. Two suppliers are cheaper, by a hundred and sixty-eight and five hundred and thirty-four rupees, but both arrive a day later. Independent verification recomputes stock, capacity and cash; it does not call the planner. Nothing has executed.

**Voice.** rate +8%, natural pitch. Measured. Stress “deterministic mode” and “nothing has executed”.

---

## 06 — SCN-010 credit review (0:55)

**Visual.**
1. Sidebar **Recommendation mode** → **Policy-grounded LLM**. Select `SCN-010 · Overdue retailer`. Run.
2. Keep 3–4 s of spinner, jump-cut.
3. Result: **What this means** and the assessment metrics.
4. Open **Evidence & unknowns**; highlight the outstanding balance and exposure lines.
5. Open **Policy basis**; highlight `POL-LIQ-007` and `POL-SVC-009`.

**Narration.**
Retailer side: a new order arrives from RET-016, who already carries an overdue balance. Supplier side: the ledger holds that balance and the credit limit on the decision date.

RET-016 owes fifty-seven thousand four hundred and forty-eight rupees and twenty-three paise. The new thirty-kilogram order adds four thousand six hundred and twenty rupees, taking exposure to sixty-two thousand and sixty-eight rupees. Policy-grounded mode gives the model a short list of eligible options. It selects hold for a human credit decision. The exposure and the limit were computed by the application, not the model, and it cannot approve the order. The card cites the liquidity and service policies in force on that date. Evidence and unknowns stay separate. Approval records the decision in the ledger only; the credit limit, order and customer record stay unchanged.

**Voice.** rate +8%, natural pitch. Neutral, precise. Stress “not the model” and “cannot approve”.

---

## 07 — SCN-013 batch recall (0:44)

**Visual.**
1. Fresh Scenario lab, **Policy-grounded LLM**, `SCN-013 · Batch recall and quality hold`, with no earlier result on screen. Hold the scenario card for 11.5 s.
2. Run; cut at the result reveal.
3. Result: **What this means**, then the step trace and the **Options compared** rows.
4. **Assessment**: recall notice, affected stock, the four open orders using the SKU.
5. **Policy basis**: `POL-STK-007`, then hold the decision block.

**Narration.**
Supplier side: the quality team flags a batch and asks for a hold. Retailer side: open orders already reference that batch, so the hold has a service cost.

Batch BATCH-004 holds three hundred pieces of SKU-005, and four open orders already reference it. Policy-grounded mode asks the model to choose between quarantine and release. It selects quarantine and cites the stock policy. The application traces every affected order. Policy POL-STK-007 requires the hold before any further dispatch. Nothing is written back to stock and no customer message is sent. The system prepares the quarantine decision; a person authorises it.

**Voice.** rate +8%, natural pitch. Calm, serious. Stress “a person authorises it”.

---

## 08 — SCN-015 route delivery, load options (0:53)

**Visual.**
1. Mode stays **Policy-grounded LLM**. Select `SCN-015 · Dispatch under vehicle capacity`. Run; jump-cut.
2. Result: **What this means** and the route metrics.
3. **Assessment**: vehicle and route, then the load order.
4. Hold **Options considered**: selected orders 0001 + 0018 at 26/40 units, against orders 0001 + 0006 at 38/40 with one promise at risk.
5. Open **Evidence & unknowns** and **Policy basis**; end on the policy-grounded check and the dispatcher decision block.

**Narration.**
Route delivery. Retailer side: three orders are promised today and tomorrow. Supplier side: all three sit on one route record, and the van cannot take everything.

Route R T E one, van A P nine: forty units, three orders, forty-seven units of demand. Seven load plans fit; loading all three exceeds the van by seven units. The application computes every plan. In policy-grounded mode, the model chooses among them and confirms the selected load with a policy citation. The largest feasible load, orders one and six, packs thirty-eight of forty, but defers order eighteen, promised today. The selected plan loads orders one and eighteen, twenty-six units, defers order six, and risks no promise. The dispatcher can approve it, or send it back; nothing leaves the depot without that decision.

**Voice.** rate +8%, natural pitch. Even, factual. Let the two load numbers land separately: “thirty-eight of forty”, then “twenty-six units”.

---

## 09 — Evaluation workspace (0:43)

**Visual.**
1. Open **Evaluation**. Show both evaluation cards.
2. **RAG results** tab: primary @1, recall @3, MRR, baseline comparison, citation coverage.
3. Switch to **Extraction results**: rules versus validated LLM, exact records, validation rate, fallbacks, latency.

**Narration.**
Evaluation. Retrieval is measured on forty frozen questions. The curated BM25 index ranks the expected document first seventy-seven point five percent of the time, finds it in the top three every time, and scores zero point eight five one MRR; simple term counting scores fifty-five percent. All six review-card citations carry a document, quote and effective date.

Extraction is measured on twelve held-out messages. The validated LLM raises intent accuracy to fifty-eight point three percent and validation to eighty-three point three; rules still win exact records, eight point three against zero. The model proposes, the validator decides, and rules remain the fallback.

**Voice.** rate +10%, natural pitch. Efficient, evidence-led. Emphasise “validator decides”.

---

## 10 — Gold set (0:24)

**Visual.**
1. Open **Track B evidence** → **Gold set**.
2. Hold the summary: 80 cases, 80 passed, 100%, p50 and p95.
3. Scroll the group coverage table: authority and security, canonical scenario, edge case, inbound persistence, intent variant, multi-turn, restatement.
4. Hold “failure labels: none”.

**Narration.**
The gold set is eighty frozen cases across seven groups: authority, canonical, edge cases, inbound persistence, intent variants, multi-turn and restatement. Sixty development, twenty confirmation. Each checks routing, review status, verification, citations, duplicates and the no-autonomous-action invariant. All eighty pass, no failure labels.

**Voice.** rate +10%, natural pitch. Brisk list, then slow for “no failure labels”.

---

## 11 — Retrieval upgrades (0:47)

**Visual.**
1. Click **Retrieval upgrades**.
2. Hold the five summary cards: 33-document runtime corpus, 513-document expanded corpus, 100% runtime recall@3, best expanded recall@3, 12 strategies.
3. Scroll to the **Every strategy** table; hold the Chunking and Retrieval columns across the 12 rows.
4. Hold `base_section_bm25` at 100% recall@3 / 0.851 MRR and `expanded_paragraph_bm25` at 97.5% recall@3.
5. Hold the runtime-corpus callout.

**Narration.**
Retrieval upgrades. Twelve strategies run on the same forty queries. Three chunkings: whole sections, paragraphs capped at one hundred and eighty words, and fixed one-hundred-and-sixty-word windows with forty words of overlap. Five retrievals: BM25, BM25 with reranking, a dense hashing embedding, hybrid fusion, and hybrid with reranking. The embedding is deterministic lexical hashing, not a neural model.

The best expanded strategy, paragraph BM25, reached ninety-seven point five percent recall at three. The curated thirty-three-document section index stays at one hundred percent, with zero point eight five one MRR. That is why runtime stays on the small index: most accurate, most auditable.

**Voice.** rate +10%, natural pitch. Neutral on the negative result; confident on the conclusion.

---

## 12 — Prompting strategies (0:23)

**Visual.**
1. Click **Prompting strategies**.
2. Hold the comparison table.
3. Highlight few-shot validation 100%, exact records 4/12, tokens 14,119.
4. Highlight zero-shot 10,095 tokens and 2 fallbacks.

**Narration.**
Prompting. Five strategies on twelve held-out messages. Few-shot lifts stated-entity accuracy to fifty-six point five percent, exact records to four of twelve, and validation to one hundred percent, with no fallbacks; it costs fourteen thousand one hundred and nineteen tokens. Zero-shot used ten thousand and ninety-five and fell back twice. The trade-off is measured, not assumed.

**Voice.** rate +10%, natural pitch. Slight lift on “measured, not assumed”.

---

## 13 — Agent runtime (0:43)

**Visual.**
1. Click **Agent runtime**.
2. Hold the completion, tool-call and latency cards: 17/17 complete, 4.47 calls, 250 ms median.
3. Scroll to the bounded review form and the `approve_order` rejection card.
4. Hold the rejection line and the 5/10 step trace with `deterministic_fallback`.

**Narration.**
Agent runtime. Seventeen of seventeen frozen tasks complete, at four point four seven tool calls and two hundred and fifty milliseconds median. Behind that, seven read-only tools. The planner is rules, not a model: it turns the intent into an ordered plan. The executor is the only place tools run; it enforces ten calls, twelve thousand tokens and five seconds, and records every attempt.

The critic checks the run: every planned step ran, no tool failed, and every citation is in force; if a check fails, one retry. A supplied plan that names approve_order is rejected before execution, because no write tool exists. Human approval stays outside the agent.

**Voice.** rate +10%, natural pitch. Steady. Hard stops on “rules, not a model” and “rejected”.

---

## 14 — Safety controls (0:32)

**Visual.**
1. Click **Safety controls**.
2. Hold cache, rate limit, PII and injection cards.
3. Scroll to the corpus injection audit: 6 documents, 6 sections, 5 autonomy signals, 1 review-bypass signal.
4. Hold the approval gate and “autonomous actions: false”.

**Narration.**
Safety controls. A five-second cache, six hundred requests per minute with a burst of two hundred, and seven identifiers masked before any external model call: GSTIN, PAN, email, UPI, Aadhaar, phone and card. Retrieved text is data, never instruction. The corpus audit flags six documents and six sections, five for autonomy language and one for review bypass; flagging never changes routing. Human approval is required, and autonomous actions are off.

**Voice.** rate +8%, natural pitch. Brisk identifier list, then a flat close.

---

## 15 — Observability (0:34)

**Visual.**
1. Open **LLM observability**.
2. Hold the five totals cards.
3. **Activity** tab: by-step and by-model tables.
4. **Runs** tab: the run table and one selected trace.
5. Hold the error/fallback line.

**Narration.**
Observability. Every model and retrieval call is a local span with latency, tokens, status and application ids. This snapshot holds five hundred and forty-one model calls, five hundred and sixty-six thousand eight hundred and ninety-five reported tokens, and six thousand one hundred and thirty-six retrieval calls.

Median model latency is two point three seconds; the ninety-fifth percentile is five point one. Twelve errors and eighteen fallbacks sit next to the latency, not averaged away. Traces stay on this machine unless an exporter is configured.

**Voice.** rate +10%, natural pitch. Precise. Pause before “Twelve errors”.

---

## 16 — Knowledge base (0:25)

**Visual.**
1. Open **Knowledge** with the policy-state expander already open.
2. Hold the header metrics: documents, sections, document types, retrieval.
3. Hold the policy-state panel: 14 in force, 0 pending, with effective dates.

**Narration.**
The knowledge base holds thirty-three approved documents, two hundred and three sections and five document types. Fourteen policies are in force on the decision date, none pending; effective dates decide which rules can ground a recommendation. Search runs on a local BM25 index over sections, returning one best section per document. Retrieval is deterministic and auditable.

**Voice.** rate +8%, natural pitch. Calm, closing cadence.

---

## 17 — Closing card (0:18)

**Visual.** Same navy card. Lines animate in sequence:
`15 scenarios · 80 frozen cases · 12 retrieval strategies · 17 agent tasks`
`Human approval on every operational decision`
Wordmark and small line: *BharatBiz Operations*.

**Narration.**
One controlled path from message to decision. Five case walks, fifteen scenarios, an eighty-case gold set, measured retrieval and prompting, a bounded agent, and a person at the end. BharatBiz Operations. Evidence in, decision out, accountability kept.

**Voice.** rate +0%, natural pitch. Warm, unhurried. Beat before the last line.

---

## Scenario mode map

| Run | Mode | What the model does |
|---|---|---|
| Inbox clarification | Policy-grounded LLM | Live extraction of intent and fields with source spans; validator accepts or rejects |
| SCN-003 supplier delay | Deterministic | None; fixed ranking rules and arithmetic only |
| SCN-010 credit review | Policy-grounded LLM | Chooses hold from precomputed eligible options; app computes exposure and rechecks citation |
| SCN-013 batch recall | Policy-grounded LLM | Chooses quarantine from precomputed options; app traces affected orders |
| SCN-015 route delivery | Policy-grounded LLM | Chooses the selected load from the computed feasible plans; app rechecks the policy citation |

Four of the five runs are model-backed; SCN-003 is retained in deterministic mode only to show the calculation path without a model, and the narration says so at the start of the segment.

---

## Modulation table

| Segment | Rate | Pitch | Intent |
|---|---|---|---|
| 00 Title card | +0% | natural | Warm, deliberate, not low |
| 01 The decision path | +6% | natural | Warm, explanatory |
| 02 Control room | +8% | natural | Crisp, operational |
| 03 Live intake | +8% | natural | Conversational |
| 04 Decision desk | +8% | natural | Even spacing, slow close |
| 05 SCN-003 supplier delay | +8% | natural | Measured, precise |
| 06 SCN-010 credit review | +8% | natural | Neutral, exact |
| 07 SCN-013 batch recall | +8% | natural | Calm, serious |
| 08 SCN-015 route delivery | +8% | natural | Even, two load numbers land |
| 09 Evaluation | +10% | natural | Efficient, evidence-led |
| 10 Gold set | +10% | natural | Brisk list, slow close |
| 11 Retrieval upgrades | +10% | natural | Neutral result, confident conclusion |
| 12 Prompting strategies | +10% | natural | Slight lift on “measured” |
| 13 Agent runtime | +10% | natural | Steady, hard stops |
| 14 Safety controls | +8% | natural | Brisk list, flat close |
| 15 Observability | +10% | natural | Precise |
| 16 Knowledge base | +8% | natural | Calm, closing cadence |
| 17 Closing card | +0% | natural | Warm, unhurried |

---

## Voice reference

The reference note (`WhatsApp Ptt 2026-11-24 at 21.18.20`) was analysed for pitch and pacing, then used as the target for the synthetic narration. It was not cloned; this toolchain has no voice-cloning step, and the recording is not reused as audio.

| Measure | Reference note | v4 narration | v5 narration | v6 narration |
|---|---|---|---|---|
| Median F0 | 91.4 Hz | ~100–102 Hz with lowered pitch | same pitch settings as v4 | 115.1 Hz, natural pitch |
| Articulation rate | 3.55 syllables/s | body +8% to +12% | unchanged; overview and scenarios split into sentence groups | body +6% to +10%; every segment recut to its own sentence groups |

V6 replaces the lowered `en-IN-PrabhatNeural` setting with `en-US-AndrewMultilingualNeural` at +0 Hz. The median F0 rises from about 100 Hz to 115 Hz, which removes the strained low register that made the delivery sound awkward. Rates were reduced by about two points because the new voice speaks faster at the same setting; the measured runtime is 11:11, still inside the 10–15 minute brief. The intro and close keep their unhurried rates.

If the final video should carry the exact recorded voice, record the script per segment; the texts in `tmp/video/narration_v5.json` and `tmp/video/segments_v4.json` are the same words used for the current cut, and the clip plan can be rebuilt against new audio without changing the visuals.

---

## Production notes

- Twelve recordings supply the cut: Act 1 = Overview → Scenario lab (SCN-003/010); Act 2 = Track B evidence (gold set, retrieval, prompting, agent, safety); Act 3 = Knowledge; Act 4 = Evaluation → LLM observability; Act 5 = Inbox retailer clarification; Act 6 = Decision desk; Act 7 = SCN-015 rerun in policy-grounded LLM mode; Act 8 = focused re-record of the retrieval-upgrades scroll; Act 9 = overview re-recorded in LLM mode with a beat mark at each narration group; Act 10 = SCN-015 setup and result in LLM mode; Act 11 = SCN-013 re-recorded from a fresh workspace in LLM mode, with a clean setup frame and the real batch-recall result; Act 12 = opening control-room shot in LLM mode with tile-by-tile highlights.
- The cut opens on the control room (Act 12), explains the same screen in five narration beats (Act 9), then goes to Inbox, the decision desk, SCN-003, SCN-010, SCN-013 and SCN-015. SCN-011 scheme claim is not in this cut. Every scenario opens with the same two-sided framing: what the retailer side reports, and what the supplier-side record confirms.
- SCN-003 is the only deterministic run and its narration opens by saying so. Inbox runs a live extraction call; SCN-010, SCN-013 and SCN-015 run in policy-grounded LLM mode, and so do the opening and overview shots. This is visible in the sidebar mode selector in each segment. The earlier deterministic SCN-013 footage, which showed a stale scheme-claim setup, is not used.
- Runtime stays on the curated 33-document section index for citing; the 513-document corpus and 12 strategies are an offline upgrade experiment on the same 40 frozen queries. The embedding is deterministic char/word hashing (blake2b, 512d), not a neural model, and the narration says that explicitly.
- Chapter pills run 01 through 15 and appear in ascending order. The overview shares the 01 Control room pill with the opening shot, so no separate 02 pill is drawn; the next pill in the cut is 02 Live intake.
- V6 runs the picture faster to match the shorter narration instead of holding on frozen frames: overview beats 3–4 1.65× and 1.54×, inbox 1.58×, decision 1.34×, SCN-003 result 1.52×, SCN-010 setup 1.60×, SCN-013 result 1.42×, SCN-015 setup 1.66× and result 1.28×, evaluation 1.46×, retrieval 1.16×, prompting 1.21×, agent 1.32×, safety 1.24×, observability 1.39×, knowledge 1.26×, close 1.55×. The setup moves remain readable and every result card is reached before its segment ends.
- The decision-desk clip starts 9.5 s in so the reviewer decision block lands under the approval narration. The prompting clip ends 0.5 s early so the next chapter pill cannot show through. The route-delivery clip drops its static tail and ends on the policy-grounded check.
- In the live intake scene, the retailer message deliberately omits product, order and date. The first send returns a single clarification question; the reply resolves the product to SKU-009 and the only open order, ORD-0024.
- Run every scenario with **Persist the outcome in the SQLite review queue** unchecked, so the pending reviews remain stable for the Decision desk segment.
- Do not click **Approve plan**, **Reject plan** or **Mark reviewed** at any point.
- Scenario setup clips run from the scenario selection to the point where the result is fully visible, so SCN-003, SCN-010 and SCN-015 include a short compressed spinner before the reveal. SCN-013 is cut tighter: its setup ends on **Run selected scenario** and the result starts on the fully visible batch-recall card, skipping the 8.7 s wait. Each clip is trimmed to its narration duration plus 0.45 s of tail.
- Observability totals: 541 model calls, 566,895 reported tokens (504,032 prompt / 62,863 completion), 6,136 retrieval calls, 8,147 spans, 876 tool calls, P50 2,342 ms, P95 5,125 ms, 12 errors, 18 rules fallbacks. The extraction table also shows validation 83.3% against 58.3% rules, and exact records 0.0% against 8.3%.
- The agent segment is deliberately deterministic: the planner is a rules planner, and there are no model calls in the frozen agent evaluation. This is stated in the narration rather than presented as a model-driven agent.
- The walkthrough never uses the words “demo”, “synthetic”, “prototype” or “test data”. It describes the running workspace.
- Master audio is loudness-normalised to −16 LUFS integrated with a −1.5 dBTP ceiling; the file decodes cleanly end to end.
