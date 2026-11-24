# BharatBiz AI Capstone — Quick Start

Run the API and operations dashboard locally on Windows. All data is synthetic; recommendations are advisory and require human approval.

## 1. Prerequisites

- Windows with PowerShell
- Python 3.11 or newer
- Git
- The project folder (example path: `C:\path\to\bharatbiz-ai-capstone-inventory-review`)

## 2. One-time setup

Open PowerShell in the project folder:

```powershell
cd C:\path\to\bharatbiz-ai-capstone-inventory-review

py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks the activate script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

The committed synthetic data is already sufficient. Only run this if you deliberately want to regenerate it:

```powershell
python scripts\generate_synthetic_data.py
```

## 3. Optional: enable the LLM

Without this, the app still runs with rules-based extraction and deterministic mode.

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in:

```text
LLM_PROVIDER=<provider>
LLM_BASE_URL=<gateway-url>
LLM_MODEL=<model-name>
LLM_API_KEY=<your-key>
LLM_CA_BUNDLE=vm05-ca.crt
```

Verify:

```powershell
python scripts\check_llm.py
```

Never commit `.env`.

## 4. Start the API — Terminal 1

```powershell
cd C:\path\to\bharatbiz-ai-capstone-inventory-review
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

- Health check: <http://127.0.0.1:8011/health>
- API docs: <http://127.0.0.1:8011/docs>

Keep this terminal running.

## 5. Start the dashboard — Terminal 2

Open a second PowerShell window:

```powershell
cd C:\path\to\bharatbiz-ai-capstone-inventory-review
.venv\Scripts\Activate.ps1
$env:BHARATBIZ_API_URL = "http://127.0.0.1:8011"
python -m streamlit run app/dashboard/chat.py --server.address 127.0.0.1 --server.port 8511
```

Open: <http://127.0.0.1:8511>

The `BHARATBIZ_API_URL` line is required when the API uses port 8011. Set it in the same terminal that runs Streamlit.

## 6. 60-second smoke test

1. Open **Scenario lab**.
2. Set **Recommendation mode** to `Policy-grounded LLM` (or `Deterministic`).
3. Select **SCN-015 · Dispatch under vehicle capacity**.
4. Click **Run selected scenario**.
5. Confirm the review shows:
   - 26 of 40 units loaded
   - 7 feasible plans compared, each rejected plan with its reason
   - `POL-SVC-009` cited in policy mode
   - a human-approval step and "nothing is dispatched"

Deterministic mode applies a fixed rule without calling the model. Policy-grounded mode requires the model to confirm a supplied outcome with citations or abstain explicitly; it never falls back silently. Three scenarios apply the selected mode: SCN-015 (POL-SVC-009), SCN-010 credit review (POL-LIQ-007) and SCN-013 batch recall (POL-STK-007). SCN-011, SCN-012 and SCN-014 report deterministic findings and the dashboard states that the mode was not applied.

Both modes can legitimately pick the same outcome: the model may only confirm an option that was already verified, never invent one. The difference is who decided. In deterministic mode the review card says "Deterministic · no model", the rationale says no model was called, and every policy passage is labelled "Reference only". In policy-grounded mode it says the model confirmed the choice and shows the cited documents.

For a binary comparison, run **SCN-010**: holding the order is selected, pausing existing orders is rejected as more restrictive, and accepting the order is shown as infeasible. **SCN-013** compares quarantining the batch with releasing it.

## 7. Optional: model observability

Open **LLM observability** in the dashboard after running a scenario with **Persist the outcome** ticked, sending an inbound message, or running the LLM evaluation. Each run appears as a trace; each model call, retrieval call and rules fallback appears as a span with latency, gateway-reported tokens, status and the ids used.

- The store is local: `data/runtime/traces.sqlite3` (override with `BHARATBIZ_TRACE_DB`).
- Raw data: `GET /api/v1/observability` and `GET /api/v1/observability/traces/{trace_id}`.
- Prompts and message bodies are not stored. Cost is shown only when `BHARATBIZ_TRACE_COST_PER_1K_TOKENS` is set; it is an illustrative estimate.
- Langfuse export is off by default. To also send spans to Langfuse, set `BHARATBIZ_TRACE_EXPORT=langfuse`, `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in `.env` and restart the API. This ingestion hook has not been verified against a live Langfuse instance.
- A deterministic run with rules extraction and no persisted review makes no model or retrieval call, so it records no span. That is expected.

## 8. Useful commands

Run tests:

```powershell
python -m pytest -q
```

Run the scenario evaluator (expects 15/15):

```powershell
python scripts\evaluate_scenarios.py
```

Reset demo data (clears the review queue, chats, retailer history and model traces):

```powershell
python scripts\reset_demo.py
```

Or use **Reset demo** in the sidebar.

Run a scenario from the CLI:

```powershell
python scripts\run_scenario.py --scenario SCN-015 --mode mock
```

## 9. Troubleshooting

**Port already in use**

```powershell
netstat -ano | findstr :8011
taskkill /PID <pid> /F
```

**Dashboard says it cannot reach the API**

- Confirm the API is running at <http://127.0.0.1:8011/health>.
- Confirm `$env:BHARATBIZ_API_URL` was set in the Streamlit terminal.
- Restart the Streamlit terminal after changing the variable.

**"Policy-grounded LLM is not configured"**

- Check `.env` contains `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`.
- Run `python scripts\check_llm.py`.
- Restart the API after editing `.env`.

**Dashboard opens but shows no data**

- Make sure the commands ran from the project root.
- Check that `data\synthetic\business_state.json` exists.

## Demo guardrails

- Academic synthetic simulation only.
- Recommendations require human approval.
- No purchases, payments, stock mutations, credit decisions or outbound messages are executed.
- Do not put real retailer, supplier or credential data into the demo.
