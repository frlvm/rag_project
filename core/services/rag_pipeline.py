from core.services.retriever import retrieve_chunks
from core.services.prompt_builder import build_prompt
from core.services.gigachat_client import ask_gigachat


def answer_question(question, subject):
    documents, metadatas = retrieve_chunks(
        question=question,
        subject=subject,
        top_k=5
    )
    print("METADATA ", metadatas)
    prompt = build_prompt(documents, metadatas, question)

    return ask_gigachat(prompt)