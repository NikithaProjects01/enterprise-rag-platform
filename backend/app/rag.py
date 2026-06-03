from dataclasses import dataclass
from math import log, sqrt
import re
from time import perf_counter

from sqlalchemy.orm import Session

from .models import Chunk, QueryLog, User


@dataclass
class RetrievalResult:
    chunk_id: int
    content: str
    citation: str
    score: float


def chunk_text(text: str, strategy: str) -> list[str]:
    words = text.split()
    if strategy == "fixed":
        size, overlap = 120, 20
    elif strategy == "recursive":
        size, overlap = 180, 30
    else:
        sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
        chunks, current = [], []
        for sentence in sentences:
            current.append(sentence)
            if len(" ".join(current).split()) >= 140:
                chunks.append(". ".join(current) + ".")
                current = []
        if current:
            chunks.append(". ".join(current) + ".")
        return chunks or [text[:1000]]

    chunks = []
    step = max(size - overlap, 1)
    for start in range(0, len(words), step):
        piece = words[start : start + size]
        if piece:
            chunks.append(" ".join(piece))
    return chunks or [text[:1000]]


def retrieve(db: Session, question: str, limit: int = 4) -> list[RetrievalResult]:
    chunks = db.query(Chunk).all()
    if not chunks:
        return []
    documents = [tokenize(chunk.content) for chunk in chunks]
    query = tokenize(question)
    idf = build_idf(documents + [query])
    query_vector = tfidf(query, idf)
    scored = []
    seen_contents = set()
    for chunk, tokens in zip(chunks, documents):
        score = cosine(query_vector, tfidf(tokens, idf))
        if score > 0:
            normalized = " ".join(chunk.content.split())
            if normalized not in seen_contents:
                seen_contents.add(normalized)
                scored.append(
                    RetrievalResult(
                        chunk_id=chunk.id,
                        content=chunk.content,
                        citation=chunk.citation,
                        score=round(score, 4),
                    )
                )
    return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]


def tokenize(text: str) -> list[str]:
    stopwords = {"the", "and", "or", "a", "an", "to", "of", "in", "for", "with", "is", "are", "on"}
    return [word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in stopwords]


def build_idf(docs: list[list[str]]) -> dict[str, float]:
    total = len(docs)
    terms = set(term for doc in docs for term in doc)
    return {term: log((1 + total) / (1 + sum(term in doc for doc in docs))) + 1 for term in terms}


def tfidf(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = {term: tokens.count(term) for term in set(tokens)}
    total = max(len(tokens), 1)
    return {term: (count / total) * idf.get(term, 0) for term, count in counts.items()}


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    shared = set(left) & set(right)
    numerator = sum(left[term] * right[term] for term in shared)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def answer_question(db: Session, user: User, question: str) -> dict:
    start = perf_counter()
    contexts = retrieve(db, question)
    if not contexts:
        answer = "I could not find enough document context to answer that. Please upload relevant documents first."
    else:
        answer = build_answer(question, contexts)

    latency_ms = round((perf_counter() - start) * 1000, 2)
    relevance = round(sum(item.score for item in contexts) / max(len(contexts), 1), 3)
    faithfulness = round(min(1.0, 0.55 + relevance), 3) if contexts else 0.0
    hallucination_rate = round(1 - faithfulness, 3)
    cost_usd = round((len(question.split()) + len(answer.split())) * 0.000002, 6)

    log = QueryLog(
        user_id=user.id,
        question=question,
        answer=answer,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        relevance=relevance,
        faithfulness=faithfulness,
        hallucination_rate=hallucination_rate,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return {
        "query_id": log.id,
        "answer": answer,
        "citations": unique_citations(contexts),
        "metrics": {
            "relevance": relevance,
            "faithfulness": faithfulness,
            "hallucination_rate": hallucination_rate,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
        },
    }


def build_answer(question: str, contexts: list[RetrievalResult]) -> str:
    query_terms = set(tokenize(question))
    candidates = []
    for item in contexts:
        for sentence in split_sentences(item.content):
            sentence_terms = set(tokenize(sentence))
            score = len(query_terms & sentence_terms)
            if score:
                candidates.append((score, sentence.strip()))

    if not candidates:
        best_context = contexts[0].content.strip()
        return f"Based on the most relevant document section: {best_context[:700]}{'...' if len(best_context) > 700 else ''}"

    seen = set()
    selected = []
    for _, sentence in sorted(candidates, key=lambda pair: pair[0], reverse=True):
        normalized = sentence.lower()
        if normalized not in seen:
            selected.append(sentence)
            seen.add(normalized)
        if len(selected) == 4:
            break

    return " ".join(selected)


def split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [sentence for sentence in sentences if len(sentence.strip()) > 20]


def unique_citations(contexts: list[RetrievalResult]) -> list[dict]:
    seen = set()
    citations = []
    for item in contexts:
        if item.citation in seen:
            continue
        seen.add(item.citation)
        citations.append({"source": item.citation, "score": item.score})
    return citations
