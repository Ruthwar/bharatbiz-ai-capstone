import json
from datetime import date
from pathlib import Path

import pytest

from app.orchestration.review import build_review_context
from app.orchestration.workflow import process_message
from app.rag.corpus import DEFAULT_CORPUS_DIR, CorpusError, load_documents
from app.rag.retrieval import RagIndex, retrieve
from app.schemas.contracts import MessageSubmission

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((PROJECT_ROOT / "data" / "eval" / "golden_queries.json").read_text(encoding="utf-8"))
SCENARIO_DATE = date(2026, 11, 1)


@pytest.fixture(scope="module")
def index() -> RagIndex:
    built = RagIndex(":memory:")
    built.ensure()
    return built


def test_every_document_carries_provenance():
    for document in load_documents():
        assert document.status in {"approved", "reference"}, document.document_id
        assert document.licence, document.document_id
        assert date.fromisoformat(document.effective_from)
        assert document.sections, document.document_id
        if document.classification == "public_regulation":
            assert document.source_url.startswith("https://"), document.document_id
            assert document.retrieved_on, document.document_id
        else:
            assert document.classification == "synthetic", document.document_id
            assert document.source_url == "", document.document_id
            assert "SIMULATION ONLY" in document.sections[0].text.upper() or any(
                "SIMULATION ONLY" in section.text.upper() for section in document.sections
            ), document.document_id


def test_corpus_has_no_duplicate_ids_or_sections():
    documents = load_documents()
    assert len(documents) == len({document.document_id for document in documents})
    section_ids = [section.section_id for document in documents for section in document.sections]
    assert len(section_ids) == len(set(section_ids))


def test_non_conforming_document_is_rejected(tmp_path):
    path = tmp_path / "BROKEN-001.md"
    path.write_text("---\ndocument_id: BROKEN-001\ntitle: Broken\n---\nbody\n", encoding="utf-8")
    with pytest.raises(CorpusError):
        load_documents(tmp_path)


def test_retrieval_is_deterministic(index):
    query = "supplier delay revised arrival date not confirmed"
    first = [hit["document_id"] for hit in index.search(query, top_k=5)]
    second = [hit["document_id"] for hit in index.search(query, top_k=5)]
    assert first == second
    assert first


def test_empty_or_noise_queries_return_nothing(index):
    assert index.search("") == []
    assert index.search("the of and") == []
    assert index.search("zzqqxx") == []


def test_hits_carry_a_quote_and_a_citable_section(index):
    for hit in index.search("What is the minimum cash buffer", top_k=3):
        assert hit["quote"]
        assert hit["section_id"].startswith(hit["document_id"] + "#")
        assert hit["effective_from"]
        assert hit["licence"]


def test_doc_type_filter_is_applied(index):
    hits = index.search("minimum order quantity quote validity delay notice", top_k=5, doc_types=["supplier_terms"])
    assert hits
    assert {hit["doc_type"] for hit in hits} == {"supplier_terms"}


def test_supplier_filter_excludes_other_suppliers_terms(index):
    hits = index.search("minimum order quantity quote validity", top_k=8, supplier_id="SUP-003")
    document_ids = {hit["document_id"] for hit in hits}
    assert "TRM-SUP-002" not in document_ids
    assert "TRM-SUP-005" not in document_ids


def test_as_of_excludes_documents_not_yet_in_force(index):
    hits = index.search("supplier delay cash buffer substitution", top_k=8, as_of=date(2026, 1, 1))
    assert all(hit["effective_from"] <= "2026-01-01" for hit in hits)
    assert "SOP-INT-001" not in {hit["document_id"] for hit in hits}


def test_golden_queries_meet_the_floor(index):
    primary = 0
    hits_at_3 = 0
    reciprocal = 0.0
    for case in GOLDEN["queries"]:
        ranked = [hit["document_id"] for hit in index.search(case["query"], top_k=5)]
        accepted = {case["expected"], *case.get("acceptable", [])}
        primary += bool(ranked) and ranked[0] == case["expected"]
        hits_at_3 += bool(accepted & set(ranked[:3]))
        reciprocal += 1 / (ranked.index(case["expected"]) + 1) if case["expected"] in ranked else 0.0
    total = len(GOLDEN["queries"])
    assert hits_at_3 / total >= 0.93, f"recall@3 {hits_at_3 / total:.2%}"
    assert primary / total >= 0.70, f"primary@1 {primary / total:.2%}"
    assert reciprocal / total >= 0.78, f"MRR {reciprocal / total:.3f}"


def test_review_card_gets_effective_citations():
    fixture = json.loads(
        (PROJECT_ROOT / "data" / "synthetic" / "scenario_fixtures" / "SCN-003.json").read_text(encoding="utf-8")
    )
    result = process_message(MessageSubmission.model_validate(fixture["message"]))
    context = build_review_context(result)
    references = context["references"]

    assert context["references_error"] is None
    assert len(references) == 3
    assert {"POL-DLY-001", "POL-CSH-002"} <= {reference["document_id"] for reference in references}
    for reference in references:
        assert reference["quote"]
        assert reference["effective_from"] <= SCENARIO_DATE.isoformat()
        assert reference["licence"]
        assert reference["source_url"] is None


def test_module_level_retrieve_reads_the_same_corpus(index):
    assert DEFAULT_CORPUS_DIR.is_dir()
    hits = retrieve("Rule 6 declarations on every package", top_k=1)
    assert hits[0]["document_id"] == "REG-LMPC-2011-R6"
