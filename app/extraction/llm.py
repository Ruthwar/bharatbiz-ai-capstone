"""OpenAI-compatible chat-completions adapter. Disabled unless explicitly configured by environment."""

import json
import logging
import os
import time

import httpx

from app.extraction.base import Extraction
from app.extraction.prompts import EXTRACTION_PROMPT_VERSION, SYSTEM_PROMPT
from app.orchestration.taxonomy import INTENTS, UNCLASSIFIED
from app.schemas.contracts import BusinessState, EvidenceFact, IntentMatch, MessageSubmission

logger = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    pass


class LLMExtractor:
    name = "llm"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 20.0,
        ca_bundle: str | None = None,
        json_mode: str = "json_object",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.ca_bundle = ca_bundle
        self.json_mode = json_mode

    @classmethod
    def from_environment(cls) -> "LLMExtractor | None":
        if os.getenv("LLM_PROVIDER", "none").lower() in {"", "none", "rules", "mock"}:
            return None
        base_url = os.getenv("LLM_BASE_URL", "")
        api_key = os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL", "")
        if not (base_url and api_key and model):
            return None
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
            ca_bundle=os.getenv("LLM_CA_BUNDLE") or None,
            json_mode=os.getenv("LLM_JSON_MODE", "json_object"),
        )

    def extract(self, message: MessageSubmission, state: BusinessState) -> Extraction:
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 512,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Catalogue products: "
                        + json.dumps(
                            [
                                f"{product['product_name']} {product['pack_description']}"
                                for product in state.products
                            ],
                            ensure_ascii=False,
                        )
                        + "\n\nMessage:\n<<<\n"
                        + message.text
                        + "\n>>>"
                    ),
                },
            ],
        }
        if self.json_mode and self.json_mode.lower() != "none":
            payload["response_format"] = {"type": self.json_mode}

        started = time.monotonic()
        try:
            with httpx.Client(
                timeout=self.timeout_seconds, verify=self.ca_bundle or True, trust_env=False
            ) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:200].replace("\n", " ")
            raise ExtractionError(f"model call failed: HTTP {exc.response.status_code} {detail}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ExtractionError(f"model call failed: {type(exc).__name__}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ExtractionError("model returned unparseable JSON") from exc

        extraction = self._build(parsed)
        usage = body.get("usage") or {}
        logger.info(
            "extraction_completed provider=%s model=%s prompt_version=%s message_id=%s "
            "latency_ms=%d prompt_tokens=%s completion_tokens=%s intents=%d facts=%d",
            self.base_url,
            self.model,
            EXTRACTION_PROMPT_VERSION,
            message.message_id,
            latency_ms,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            len(extraction.intents),
            len(extraction.facts),
        )
        return extraction

    def _build(self, parsed: dict) -> Extraction:
        intents = []
        for raw in parsed.get("intents") or []:
            intent = str(raw.get("intent", UNCLASSIFIED))
            if intent not in INTENTS and intent != UNCLASSIFIED:
                intent = UNCLASSIFIED
            try:
                confidence = float(raw.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            intents.append(
                IntentMatch(
                    intent=intent,
                    confidence=confidence,
                    evidence_span=raw.get("evidence"),
                )
            )

        facts = []
        for raw in parsed.get("facts") or []:
            field = str(raw.get("field", "")).strip()
            value = raw.get("value")
            if not field or value is None:
                continue
            evidence = raw.get("evidence")
            facts.append(
                EvidenceFact(
                    field=field,
                    value=str(value),
                    evidence_span=str(evidence if evidence is not None else value),
                )
            )

        unknowns = [str(item) for item in parsed.get("unknowns") or []]
        return Extraction(intents=intents, facts=facts, uncertainties=unknowns, mode="llm")
