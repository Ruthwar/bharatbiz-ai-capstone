# RAG corpus and source register

Every document in `data/knowledge_docs/` is listed here with its origin, licence and date. The machine-readable copy is `data/knowledge_docs/manifest.json`, rebuilt with `python scripts/build_rag_index.py`.

Two classes of document are mixed in one corpus and never blurred:

- **Synthetic** (`classification: synthetic`) — written for this capstone. Fictional parties, fictional amounts, labelled `SIMULATION ONLY` in every file, licensed CC0-1.0.
- **Public regulation** (`classification: public_regulation`) — real Government of India text, quoted in short excerpts with a source URL and retrieval date. Commentary around the quotes is this project's and is marked as such.

## 1. Synthetic corpus (27 documents)

| ID | Type | Title | Effective | Used for |
| --- | --- | --- | --- | --- |
| POL-DLY-001 | policy | Supplier Delay Handling Policy | 2026-04-01 | The ranking rule, the no-promise rule, the worked 102-unit example |
| POL-CSH-002 | policy | Cash Buffer and Affordability Policy | 2026-06-01 | Why a plan is excluded before ranking, immediate-outflow treatment |
| POL-SUB-003 | policy | Product Substitution and Equivalence Policy | 2026-07-15 | Pack-size change is substitution; no unit conversion |
| POL-DAT-004 | policy | Evidence, Consent and Data Minimisation Policy | 2026-05-20 | Verbatim spans, offsets, retrieval supplies text not numbers |
| POL-PRC-005 | policy | Price Validity and Re-approval Policy | 2026-08-01 | Approval binding, mid-delay re-quote gap |
| POL-COM-006 | policy | Retailer and Supplier Communication Policy | 2026-03-10 | Template acknowledgements, no promises |
| SOP-INT-001 | sop | Inbound Message Intake and Question SOP | 2026-09-01 | Identity gate, slots, two-question cap, forking |
| SOP-REV-002 | sop | Human Review Queue SOP | 2026-09-15 | How a reviewer reads the card, approval conditions |
| SOP-SHT-003 | sop | Partial Dispatch and Short Delivery SOP | 2026-10-01 | Why split delivery is escalated, not averaged |
| SOP-STV-004 | sop | State Version and Refresh SOP | 2026-10-05 | Version pinning, mismatch handling, reset procedure |
| TRM-SUP-002 | supplier_terms | Balaji Wholesale Distributors | 2026-04-15 | 2-day lead, 7-day payment, MOQ by SKU, 12-hour delay notice |
| TRM-SUP-003 | supplier_terms | Krishna Rice Mills | 2026-05-01 | 3-day lead, 14-day payment, 24-hour notice, 3-day price revision |
| TRM-SUP-005 | supplier_terms | Sri Venkateswara FMCG Supply | 2026-08-20 | 1-day lead, immediate delay notice, mid-delay re-quote gap |
| CASE-2026-014 | case_note | Cooking Oil Delay and the 28 Late Litres | 2026-10-20 | The demo scenario's reasoning, written up |
| CASE-2026-009 | case_note | Split Delivery at Month End | 2026-09-28 | Percentage is not a quantity; two dates cannot be averaged |
| CASE-2026-021 | case_note | Re-quote After Approval | 2026-10-30 | Approval is a snapshot, not a standing permission |
| CASE-2026-005 | case_note | Retailer Reporting a Supplier Delay | 2026-09-12 | Why the identity gate exists |
| POL-DEM-007 | policy | Demand Simulation and Scenario Policy | 2026-11-15 | Labelled scenarios, fixed state inputs and no execution |
| POL-STK-007 | policy | Physical-Stock Reconciliation Policy | 2026-11-15 | Count variance, reservations and approved stock adjustments |
| POL-LIQ-007 | policy | Liquidity and Cash-Flow Control Policy | 2026-11-15 | Cash headroom, immediate outflow and exclusion of breaches |
| POL-RCM-007 | policy | Retailer Complaints and Resolution Policy | 2026-11-15 | Complaint evidence, triage and human-approved remedies |
| POL-MSC-007 | policy | Market-Signal Corroboration Policy | 2026-11-15 | Independent corroboration and uncertainty labels |
| SOP-DEM-007 | sop | Demand Simulation SOP | 2026-11-15 | Reproducible scenario procedure and comparison outputs |
| SOP-STK-007 | sop | Physical-Stock Reconciliation SOP | 2026-11-15 | Count, recount, adjustment and plan refresh procedure |
| SOP-LIQ-007 | sop | Liquidity Monitoring and Approval SOP | 2026-11-15 | Deterministic liquidity calculation before review |
| SOP-RCM-007 | sop | Retailer Complaint Intake and Triage SOP | 2026-11-15 | Complaint intake, evidence capture and escalation |
| SOP-MSC-007 | sop | Market-Signal Collection and Corroboration SOP | 2026-11-15 | Signal collection, duplicate handling and expiry |

Consistency checks applied while writing:

- MOQ, capacity, lead time and payment terms match `data/synthetic/supplier_products.csv` and `suppliers.csv` row by row.
- The worked example uses the real fixture: 102 units requested, 56 usable, 46 bought, 12 delayed incoming units, horizon 2026-11-04.
- The cash example uses the state's actual buffer of ₹50,000 and opening cash of ₹2,50,000.
- Nothing in the policies grants the system an action the code does not take: no orders, no payments, no outbound messages.
- The five new policy/SOP pairs are synthetic, effective 2026-11-15, carry CC0-1.0 synthetic licences and contain no source URLs or real-party claims.

## 2. Regulatory extracts (3 documents)

### REG-FSSAI-LAB-2020

- **Title**: Food Safety and Standards (Labelling and Display) Regulations, 2020, Version VIII.
- **Publisher**: Food Safety and Standards Authority of India.
- **URL**: https://fssai.gov.in/docs/food-law/regulations/Comp_Labelling%20Display_Version%20VIII_09_09_2025.pdf
- **Document date**: 09.09.2025 (version page header). 39 pages.
- **Retrieved**: 2026-11-13. Text extracted with PyMuPDF; the PDF has a text layer, unlike the Consumer Affairs and Meghalaya copies of the Legal Metrology material.
- **Licence**: Government of India publication. No open licence is asserted. Short excerpts are reproduced for academic citation, with the source URL and date; this is not an official reproduction and is not legal advice.
- **Quoted provisions**: Regulation 1(2) scope; 4(3) misleading labels; 4(5) language; 4(7) legibility; 5(1) name of food; 5(2) ingredient list and the "specific edible oil" class title; 5(6)(a) name and address; 5(7)(a)-(b) FSSAI logo and licence; 5(8) net quantity, retail price and consumer care via Legal Metrology; 5(9) batch; 5(10)(a) date marking.
- **Deliberately excluded**: nutrition panel, front-of-pack warning, veg/non-veg marks, allergens, fortification, advertising claims. Out of scope for this slice.

### REG-LMPC-2011-R6

- **Title**: The Legal Metrology (Packaged Commodities) Rules, 2011 (Union of India).
- **Primary source attempted**: https://megweights.gov.in/acts/Legal-Metrology-Packaged-Commodities-Rules-2011.pdf — 38 MB, image-only; 47 pages yielded 46 characters of text, so it could not be searched. The Consumer Affairs FAQ PDF is also image-only.
- **Copy used**: https://indiankanoon.org/doc/100694501/ (consolidated Union of India Act text). Retrieved 2026-11-13.
- **Licence**: Government of India legislation. The Indian Kanoon copy is a compilation; no open licence is asserted. Short excerpts only.
- **Quoted provisions**: Rule 4 (no pre-packing without declarations); Rule 6(1) opening words and (a)-(f); Explanation III (food packages fall under the FSS Act); Rule 6(2) consumer care; Rule 6(3) stickers and the reduced-MRP exception; Rule 7 display panel.
- **Caveat**: a consolidated copy may lag the Gazette. Verify before relying on a quotation. The extract says so in its own closing section.

### REG-GST-2025-09

- **Policy source**: GST Council, 56th meeting recommendations, PIB release dated 03.09.2025 — https://gstcouncil.gov.in/sites/default/files/2025-09/press_release_press_information_bureau_0.pdf. Confirms the 5% merit rate, 18% standard rate and 40% de-merit rate.
- **Rate schedule**: CGST rates "as on 22.09.2025", Notification No. 09/2025-Central Tax (Rate) dated 17.09.2025, compiled by the Commercial Taxes Department, Government of Jammu and Kashmir — https://jkcomtax.gov.in/pdf/GST%20rates2025.pdf. The compilation lists CGST 2.5% / 9% / 20%, which is combined GST 5% / 18% / 40%.
- **Retrieved**: 2026-11-13.
- **Licence**: Government publications. The compilation carries its own disclaimer: it is for ease of reference and only Gazette notifications have legal authority. The extract repeats that disclaimer.
- **Rates recorded**: rice pre-packaged 5% (loose nil); edible oils 5%; biscuits 5%; toilet soap bars 5%; shampoo 5%; toothpaste 5%; tea 5%; detergent 18%; beverages 5% or 40% depending on the drink.
- **Caveat**: no amendment after 22.09.2025 was checked. The document says so and dates the rates.

## 3. Open Food Facts (optional, not part of the corpus)

Queried the public API on 2026-11-13 with `categories_tags_en` filtered to India, 50 products per category, to see typical Indian retail pack sizes against the 12 catalogue lines.

| Category | Products in India (API count) | Pack sizes observed |
| --- | --- | --- |
| Rice | 91 | 500 g, 1 kg, 1.5 kg |
| Sunflower oil | 42 | 1 L, 5 L, 15 L, 500 ml |
| Biscuits | 923 | 25 g to 90 g singles; family packs |
| Soap | 9 | 68 g to 150 g |
| Shampoo | 12 | 80 ml to 340 ml; sachets |
| Tea | 287 | 100 g, 250 g, 500 g, 1 kg |
| Fruit juice | 144 | 125 ml to 1 L |
| Laundry detergent | 1 | 500 g |
| Toothpaste | 15 | 20 g to 300 g |

- **Licence**: Open Database License (ODbL) 1.0 for the database; individual contents under DbCL. Attribution: "Open Food Facts, https://world.openfoodfacts.org, ODbL 1.0, retrieved 2026-11-13".
- **Use**: context only. No pack size, price or product from Open Food Facts enters the business state or the planner. The catalogue remains synthetic. Recording it here shows the check was run and what it would take to use it properly.
- **Coverage caveat**: detergent has one Indian product and soap nine, so those two categories are too thin to generalise from after brand-level filtering.

## 4. How to reproduce the extraction

```bash
python - <<'PY'
import urllib.request, pymupdf
url = "https://fssai.gov.in/docs/food-law/regulations/Comp_Labelling%20Display_Version%20VIII_09_09_2025.pdf"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
open("fssai.pdf", "wb").write(urllib.request.urlopen(req, timeout=60).read())
doc = pymupdf.open("fssai.pdf")
text = "\n".join(page.get_text() for page in doc)
open("fssai.txt", "w", encoding="utf-8").write(text)
PY
```

The GST compilation and the Council release download the same way. The Legal Metrology Rules cannot be extracted this way from the Government PDF because it is scanned; the Indian Kanoon HTML copy is text and can be stripped of tags.

## 5. Rules for adding a document

1. Frontmatter with every required field; the loader rejects a document without `document_id`, `effective_from`, `licence` and `classification`.
2. Regulatory documents must carry `source_url` and `retrieved_on`; the loader rejects them otherwise.
3. Synthetic documents must not carry a source URL and must open with `SIMULATION ONLY`.
4. A superseded document gets a new ID or a new version and an `effective_from`; never edit a rule silently in place.
5. Rebuild the index and the manifest, then re-run `scripts/eval_rag.py` and the test suite.
