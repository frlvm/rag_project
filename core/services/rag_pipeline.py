from core.services.retriever import retrieve_chunks
from core.services.prompt_builder import build_prompt
from core.services.gigachat_client import ask_gigachat


def answer_question(question, subject):
    context_chunks = retrieve_chunks(
        question=question,
        subject=subject,
        top_k=5
    )

    prompt = build_prompt(question, context_chunks)
    return ask_gigachat(prompt)
