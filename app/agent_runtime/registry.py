"""Allow-listed read-only tools over the synthetic state and the approved corpus.

There are seven tools and no write tool. Arguments are validated against each tool's
declared parameters before a handler runs, so a malformed plan fails with a label instead
of a stack trace. Every handler is a thin adapter over an existing deterministic function;
the tools add no arithmetic of their own.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.agents.cashflow import project_cash
from app.agents.inventory import analyze_inventory
from app.agents.orders import allocate_by_priority, analyze_orders
from app.agents.retailer import order_history
from app.agents.supplier import build_supplier_options
from app.agent_runtime.budget import estimate_tokens
from app.decision.selector import DecisionModeError, policy_inventory
from app.rag.retrieval import document_section, retrieve
from app.schemas.contracts import BusinessState

logger = logging.getLogger(__name__)

MAX_TOP_K = 10
_INT = re.compile(r"-?\d+")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class ToolError(Exception):
    """A tool call that must be reported, not raised, by the executor."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, dict]
    handler: Callable[..., dict] | None
    read_only: bool = True

    def describe(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "read_only": self.read_only,
            "parameters": self.parameters,
        }


@dataclass
class ToolResult:
    tool: str
    status: str
    output: dict
    args: dict
    code: str | None = None
    error: str | None = None
    latency_ms: float = 0.0
    estimated_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "status": self.status,
            "args": self.args,
            "output": self.output,
            "code": self.code,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "estimated_tokens": self.estimated_tokens,
        }


def _int_arg(name: str, value) -> int:
    if isinstance(value, bool):
        raise ToolError("malformed_arguments", f"{name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _INT.fullmatch(value.strip()):
        return int(value)
    raise ToolError("malformed_arguments", f"{name} must be an integer")


def _number_arg(name: str, value) -> Decimal:
    if isinstance(value, bool):
        raise ToolError("malformed_arguments", f"{name} must be a number")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str) and _NUMBER.fullmatch(value.strip()):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise ToolError("malformed_arguments", f"{name} is not a valid number") from exc
    raise ToolError("malformed_arguments", f"{name} must be a number")


def _validate(spec: ToolSpec, arguments: dict | None) -> dict:
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ToolError("malformed_arguments", "tool arguments must be an object")
    unknown = [key for key in arguments if key not in spec.parameters]
    if unknown:
        raise ToolError("malformed_arguments", f"unknown argument(s) for {spec.name}: {', '.join(sorted(unknown))}")
    cleaned: dict = {}
    for name, declared in spec.parameters.items():
        value = arguments.get(name)
        if value is None:
            if declared.get("required"):
                raise ToolError("malformed_arguments", f"{spec.name} requires {name}")
            continue
        kind = declared["type"]
        if kind == "str":
            if not isinstance(value, str) or not value.strip():
                raise ToolError("malformed_arguments", f"{name} must be a non-empty string")
            cleaned[name] = value.strip()
        elif kind == "int":
            cleaned[name] = _int_arg(name, value)
        elif kind == "number":
            cleaned[name] = _number_arg(name, value)
        elif kind == "array":
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ToolError("malformed_arguments", f"{name} must be an array of strings")
            cleaned[name] = list(value)
        elif kind == "units":
            cleaned[name] = value if value == "all" else _int_arg(name, value)
        elif kind == "required_units":
            cleaned[name] = value if value == "auto" else _int_arg(name, value)
        elif kind == "date_or_auto":
            if value == "auto":
                cleaned[name] = value
            elif isinstance(value, str) and _DATE.fullmatch(value.strip()):
                try:
                    cleaned[name] = date.fromisoformat(value.strip()).isoformat()
                except ValueError as exc:
                    raise ToolError("malformed_arguments", f"{name} is not a valid date") from exc
            else:
                raise ToolError("malformed_arguments", f"{name} must be YYYY-MM-DD or auto")
        else:  # pragma: no cover - a spec typo must fail loudly in tests
            raise ToolError("malformed_arguments", f"unsupported parameter type {kind}")
    return cleaned


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._specs[spec.name] = spec

    def names(self) -> list[str]:
        return list(self._specs)

    def describe(self) -> list[dict]:
        return [self._specs[name].describe() for name in self._specs]

    def spec(self, name: str) -> ToolSpec:
        if name not in self._specs:
            raise ToolError("unknown_tool", f"unknown tool: {name}")
        return self._specs[name]

    def validate_arguments(self, name: str, arguments: dict | None) -> dict:
        """Shared by the executor and by supplied-plan validation."""
        return _validate(self.spec(name), arguments)

    def call(self, name: str, arguments: dict | None = None) -> ToolResult:
        spec = self.spec(name)
        cleaned = _validate(spec, arguments)
        assert spec.handler is not None
        started = time.monotonic()
        try:
            output = spec.handler(**cleaned)
        except ToolError:
            raise
        except DecisionModeError as exc:
            raise ToolError("policy_unavailable", str(exc)) from exc
        except LookupError as exc:
            raise ToolError("not_found", str(exc)) from exc
        except ValueError as exc:
            raise ToolError("invalid_argument", str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - a tool failure is data, not a crash
            logger.warning("tool %s failed", name, exc_info=True)
            raise ToolError("internal_error", type(exc).__name__) from exc
        latency_ms = round((time.monotonic() - started) * 1000, 1)
        return ToolResult(
            tool=name,
            status="ok",
            output=output,
            args=cleaned,
            latency_ms=latency_ms,
            estimated_tokens=estimate_tokens(
                canonical_args(cleaned) + json.dumps(output, ensure_ascii=False, default=str)
            ),
        )


_SPEC_META: dict[str, dict] = {
    "policy_search": {
        "description": (
            "Search the approved policy and SOP corpus and return verbatim citations in force on the "
            "decision date. Case notes and term sheets are excluded unless requested. When event_type is "
            "given, only documents that apply to that event, party and date are returned."
        ),
        "parameters": {
            "query": {"type": "str", "required": True, "description": "reviewer question or intent phrase"},
            "top_k": {"type": "int", "required": False, "description": "number of documents, default 3"},
            "supplier_id": {"type": "str", "required": False, "description": "party scope for applicability"},
            "doc_types": {"type": "array", "required": False, "description": "optional document type filter"},
            "event_type": {"type": "str", "required": False, "description": "intent label that scopes applicability"},
        },
    },
    "policy_metadata": {
        "description": "Classify the required policy documents for an event: applicable, not yet effective, out of scope.",
        "parameters": {
            "event_type": {"type": "str", "required": False, "description": "event or intent label"},
            "supplier_id": {"type": "str", "required": False, "description": "party scope for applicability"},
        },
    },
    "inventory_position": {
        "description": "On-hand, reserved, incoming, ATP and immediately available units for one SKU.",
        "parameters": {
            "sku_id": {"type": "str", "required": True, "description": "catalogue SKU"},
            "delayed_incoming_units": {
                "type": "units",
                "required": False,
                "description": "incoming units held back, or 'all' for a delay scenario",
            },
        },
    },
    "open_orders": {
        "description": "Open orders for one SKU with requested quantities, dates and priority.",
        "parameters": {"sku_id": {"type": "str", "required": True, "description": "catalogue SKU"}},
    },
    "supplier_options": {
        "description": "Read-only supplier offers for the required quantity, with lead time, arrival and cost.",
        "parameters": {
            "sku_id": {"type": "str", "required": True, "description": "catalogue SKU"},
            "required_units": {"type": "required_units", "required": True, "description": "units to buy, or 'auto'"},
            "original_supplier_id": {"type": "str", "required": True, "description": "supplier that is delayed"},
            "delay_days": {"type": "int", "required": True, "description": "delay added to the original supplier"},
            "planning_horizon": {"type": "date_or_auto", "required": True, "description": "last acceptable arrival, or 'auto'"},
        },
    },
    "cash_position": {
        "description": "Projected ending cash and headroom above the minimum buffer after one immediate outflow.",
        "parameters": {
            "outflow_rupees": {"type": "number", "required": False, "description": "immediate outflow, default 0"},
        },
    },
    "retailer_profile": {
        "description": "Retailer record, open-order allocations and recent order history for one retailer.",
        "parameters": {"retailer_id": {"type": "str", "required": True, "description": "retailer account"}},
    },
}


def tool_catalog() -> list[dict]:
    """The registry's public contract, without handlers."""
    return [
        {"name": name, "description": meta["description"], "read_only": True, "parameters": meta["parameters"]}
        for name, meta in _SPEC_META.items()
    ]


def _citation(hit: dict) -> dict:
    return {
        "document_id": hit["document_id"],
        "title": hit["title"],
        "section": hit["heading"],
        "quote": hit["quote"],
        "effective_from": hit["effective_from"],
        "version": hit["version"],
        "licence": hit["licence"],
        "classification": hit["classification"],
        "score": hit.get("score"),
    }


def build_registry(state: BusinessState, data_dir: Path | None = None) -> ToolRegistry:
    as_of = state.as_of.date()

    def policy_search(
        query: str,
        top_k: int = 3,
        supplier_id: str | None = None,
        doc_types: list[str] | None = None,
        event_type: str | None = None,
    ) -> dict:
        limit = max(1, min(top_k, MAX_TOP_K))
        hits = retrieve(
            query,
            top_k=max(limit * 4, 12) if event_type else limit,
            doc_types=doc_types or ["policy", "sop"],
            supplier_id=supplier_id,
            as_of=as_of,
        )
        applicable: list[str] | None = None
        if event_type:
            applicable = policy_inventory(event_type, supplier_id, as_of)["applicable"]
            baseline = set(policy_inventory("baseline", supplier_id, as_of)["applicable"])
            allowed = set(applicable)
            hits = [hit for hit in hits if hit["document_id"] in allowed]
            specific = [document_id for document_id in applicable if document_id not in baseline]
            # An intent-specific rule outranks the generic decision and service policies.
            ordered = [hit for hit in hits if hit["document_id"] in specific]
            seen = {hit["document_id"] for hit in ordered}
            for document_id in specific:
                if document_id not in seen:
                    fallback = document_section(document_id)
                    if fallback is not None:
                        ordered.append(fallback)
                        seen.add(document_id)
            ordered.extend(hit for hit in hits if hit["document_id"] not in specific)
            seen.update(hit["document_id"] for hit in hits)
            for document_id in applicable:
                if len(ordered) >= limit:
                    break
                if document_id in seen:
                    continue
                fallback = document_section(document_id)
                if fallback is not None:
                    ordered.append(fallback)
                    seen.add(document_id)
            hits = ordered
        return {"query": query, "hits": [_citation(hit) for hit in hits[:limit]], "miss": not hits}

    def policy_metadata(event_type: str | None = None, supplier_id: str | None = None) -> dict:
        return policy_inventory(event_type, supplier_id, as_of)

    def inventory_position(sku_id: str, delayed_incoming_units: int | str = 0) -> dict:
        row = next((item for item in state.inventory if item["sku_id"] == sku_id), None)
        if row is None:
            raise LookupError(f"Unknown inventory SKU: {sku_id}")
        delayed = 0
        if delayed_incoming_units == "all":
            delayed = row["incoming_units"]
        else:
            delayed = int(delayed_incoming_units)
        result = analyze_inventory(state, sku_id, delayed)
        return result.model_dump(mode="json")

    def open_orders(sku_id: str) -> dict:
        result = analyze_orders(state, sku_id)
        orders = [
            {
                "order_id": row["order_id"],
                "retailer_id": row["retailer_id"],
                "retailer_name": row["retailer_name"],
                "quantity_units": row["quantity_units"],
                "unit": row["unit"],
                "requested_delivery_date": row["requested_delivery_date"],
                "priority": row.get("priority", "normal"),
            }
            for row in result.proposal["affected_orders"]
        ]
        return {
            "sku_id": sku_id,
            "orders": orders,
            "affected_order_count": result.proposal["affected_order_count"],
            "total_requested_units": result.proposal["total_requested_units"],
            "unit": result.proposal["unit"],
        }

    def supplier_options(
        sku_id: str,
        required_units: int | str,
        original_supplier_id: str,
        delay_days: int,
        planning_horizon: str | date,
    ) -> dict:
        if required_units == "auto":
            raise ToolError("malformed_arguments", "required_units must be resolved before the call")
        horizon = planning_horizon if isinstance(planning_horizon, date) else date.fromisoformat(planning_horizon)
        options = build_supplier_options(
            state,
            sku_id,
            int(required_units),
            original_supplier_id,
            int(delay_days),
            horizon,
        )
        return {
            "sku_id": sku_id,
            "required_units": int(required_units),
            "planning_horizon": horizon.isoformat(),
            "options": [option.model_dump(mode="json") for option in options],
        }

    def cash_position(outflow_rupees: Decimal = Decimal("0")) -> dict:
        projection = project_cash(state, outflow_rupees)
        return projection.model_dump(mode="json")

    def retailer_profile(retailer_id: str) -> dict:
        record = next((row for row in state.retailers if row["retailer_id"] == retailer_id), None)
        if record is None:
            raise LookupError(f"retailer {retailer_id} not found")
        allocations = [
            row.model_dump(mode="json")
            for row in allocate_by_priority(state)
            if row.retailer_id == retailer_id
        ]
        return {
            "retailer": record,
            "open_orders": allocations,
            "order_history": order_history(retailer_id, data_dir),
        }

    handlers = {
        "policy_search": policy_search,
        "policy_metadata": policy_metadata,
        "inventory_position": inventory_position,
        "open_orders": open_orders,
        "supplier_options": supplier_options,
        "cash_position": cash_position,
        "retailer_profile": retailer_profile,
    }
    registry = ToolRegistry()
    for name, meta in _SPEC_META.items():
        registry.register(
            ToolSpec(
                name=name,
                description=meta["description"],
                parameters=meta["parameters"],
                handler=handlers[name],
            )
        )
    return registry


def canonical_args(arguments: dict) -> str:
    return json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)


def argument_tokens(arguments: dict) -> int:
    return estimate_tokens(canonical_args(arguments))


def auto_horizon(state: BusinessState, orders_output: dict | None) -> str:
    requested = [row["requested_delivery_date"] for row in (orders_output or {}).get("orders", [])]
    if requested:
        return max(requested)
    return (state.as_of.date() + timedelta(days=14)).isoformat()
