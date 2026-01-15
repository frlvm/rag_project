from core.services.retriever import retrieve_chunks
from core.services.prompt_builder import build_prompt
from core.services.gigachat_client import ask_gigachat


def answer_question(question: str) -> str:
    chunks = retrieve_chunks(question)

    prompt = build_prompt(question, chunks)

    return ask_gigachat(prompt)
