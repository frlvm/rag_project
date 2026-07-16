import logging
from time import perf_counter

from core.services.gigachat_client import ask_gigachat
from core.services.logging_utils import log_event, print_rag_question_event
from core.services.prompt_builder import build_prompt
from core.services.retriever import normalize_sources, retrieve_chunks


logger = logging.getLogger("core.rag")
NO_RELEVANT_INFO_ANSWER = "В предоставленных документах нет информации об этом"


def _is_no_relevant_info_answer(answer):
    if not answer:
        return False

    normalized_answer = answer.lower().replace("ё", "е")
    return (
        NO_RELEVANT_INFO_ANSWER.lower().replace("ё", "е") in normalized_answer
        or "нет информации" in normalized_answer
        or "отсутствует информация" in normalized_answer
    )


def answer_question(question, subject, top_k=5):
    started_at = perf_counter()
    log_event(
        logger,
        logging.INFO,
        "rag_answer_started",
        subject_id=subject.id,
        question_length=len(question),
    )

    documents, metadatas = retrieve_chunks(
        question=question,
        subject=subject,
        top_k=top_k
    )

    if not documents:
        answer = NO_RELEVANT_INFO_ANSWER
        total_duration_ms = round((perf_counter() - started_at) * 1000, 2)

        log_event(
            logger,
            logging.INFO,
            "rag_answer_no_relevant_context",
            subject_id=subject.id,
            question_length=len(question),
            total_duration_ms=total_duration_ms,
        )
        print_rag_question_event(
            subject=subject,
            question=question,
            metadatas=metadatas,
            answer=answer,
            duration_ms=total_duration_ms,
            documents=documents,
        )

        return {
            "answer": answer,
            "sources": [],
            "metadatas": metadatas,
        }

    prompt_started_at = perf_counter()
    prompt = build_prompt(documents, metadatas, question)
    log_event(
        logger,
        logging.INFO,
        "prompt_built",
        subject_id=subject.id,
        documents_count=len(documents),
        metadata_count=len(metadatas),
        prompt_length=len(prompt),
        duration_ms=round((perf_counter() - prompt_started_at) * 1000, 2),
    )

    llm_started_at = perf_counter()
    answer = ask_gigachat(prompt)
    sources = normalize_sources(metadatas)
    total_duration_ms = round((perf_counter() - started_at) * 1000, 2)

    log_event(
        logger,
        logging.INFO,
        "rag_answer_finished",
        subject_id=subject.id,
        answer_length=len(answer) if answer else 0,
        llm_duration_ms=round((perf_counter() - llm_started_at) * 1000, 2),
        total_duration_ms=total_duration_ms,
    )
    print_rag_question_event(
        subject=subject,
        question=question,
        metadatas=metadatas,
        answer=answer,
        duration_ms=total_duration_ms,
        documents=documents,
    )
    if _is_no_relevant_info_answer(answer):
        sources = []

    return {
        "answer": answer,
        "sources": sources,
        "metadatas": metadatas,
    }
