from typing import Callable, TypedDict

import numpy as np

from services.chunker import Chunk
from services.embeddings import Embedding, embed_query

# A retriever maps (query_vec, query_text, k) -> ranked chunk_indices. The text is
# passed alongside the vector so lexical/hybrid arms can match it; dense arms ignore
# it. (search_chunks-backed dense, pg_trgm lexical, RRF hybrid all share this sig.)
Retriever = Callable[[list[float], str, int], list[int]]


class EvalCase(TypedDict, total=False):
    id: str
    query: str
    expected_page_start: int
    expected_page_end: int
    expected_section_substring: str
    expected_keywords: list[str]
    out_of_scope: bool
    kind: str  # "semantic" | "lexical" — groups misses for the hybrid-eval gate


class CaseResult(TypedDict):
    id: str
    query: str
    expected_indices: list[int]
    hit: bool
    first_hit_rank: int | None
    top_k_indices: list[int]
    out_of_scope: bool


class EvalReport(TypedDict):
    k: int
    cases: list[CaseResult]
    mean_recall_at_k: float
    mean_mrr: float


def retrieve(
    embeddings: list[Embedding],
    query_vec: list[float],
    query_text: str,  # unused: this in-memory dense retriever needs only the vector
    k: int = 5,
) -> list[int]:
    q = np.asarray(query_vec, dtype=np.float32)
    mat = np.asarray([e["vector"] for e in embeddings], dtype=np.float32)
    scores = mat @ q
    top = np.argsort(-scores)[:k]
    return [embeddings[i]["chunk_index"] for i in top]


def resolve_expected(case: EvalCase, chunks: list[Chunk]) -> list[int]:
    """Map durable ground truth → current chunk_indices via page-range overlap + section substring."""
    sub = case["expected_section_substring"].lower()
    return [
        c["chunk_index"]
        for c in chunks
        if c["page_start"] <= case["expected_page_end"]
        and c["page_end"] >= case["expected_page_start"]
        and sub in (c["section_title"] or "").lower()
    ]


def recall_at_k(retrieved: list[int], expected: list[int], k: int) -> float:
    if not expected:
        return 0.0
    hits = sum(1 for x in retrieved[:k] if x in expected)
    return hits / len(expected)


def mrr(retrieved: list[int], expected: list[int]) -> float:
    for rank, idx in enumerate(retrieved, start=1):
        if idx in expected:
            return 1.0 / rank
    return 0.0


def run_eval(
    cases: list[EvalCase],
    chunks: list[Chunk],
    retriever: Retriever,
    k: int = 5,
) -> EvalReport:
    case_results: list[CaseResult] = []
    for case in cases:
        oos = case.get("out_of_scope", False)
        if oos:
            expected: list[int] = []
        else:
            expected = resolve_expected(case, chunks)
            if not expected:
                raise ValueError(
                    f"case {case['id']} resolved to 0 chunks — "
                    f"check page range / section substring"
                )
        qv = embed_query(case["query"])
        top = retriever(qv, case["query"], k)
        hit_rank = next(
            (r for r, idx in enumerate(top, start=1) if idx in expected),
            None,
        )
        case_results.append(
            CaseResult(
                id=case["id"],
                query=case["query"],
                expected_indices=expected,
                hit=hit_rank is not None,
                first_hit_rank=hit_rank,
                top_k_indices=top,
                out_of_scope=oos,
            )
        )
    scored = [r for r in case_results if not r["out_of_scope"]]
    if scored:
        mean_r = sum(
            recall_at_k(r["top_k_indices"], r["expected_indices"], k) for r in scored
        ) / len(scored)
        mean_m = sum(mrr(r["top_k_indices"], r["expected_indices"]) for r in scored) / len(scored)
    else:
        mean_r = 0.0
        mean_m = 0.0
    return EvalReport(
        k=k,
        cases=case_results,
        mean_recall_at_k=mean_r,
        mean_mrr=mean_m,
    )


def print_report(report: EvalReport) -> None:
    for r in report["cases"]:
        tag = " OOS" if r["out_of_scope"] else ""
        print(
            f"[{r['id']}{tag}] hit={r['hit']} rank={r['first_hit_rank']} "
            f"expected={r['expected_indices']} top={r['top_k_indices']} "
            f"q={r['query']!r}"
        )
    print(f"\nmean Recall@{report['k']}: {report['mean_recall_at_k']:.3f} (OOS excluded)")
    print(f"mean MRR: {report['mean_mrr']:.3f} (OOS excluded)")
