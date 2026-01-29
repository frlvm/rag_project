from core.services.retriever import retrieve_chunks
from core.services.prompt_builder import build_prompt
from core.services.gigachat_client import ask_gigachat
from core.services.embeddings import embed_text


def answer_question(question, subject):
    question_embedding = embed_text(question)

    context_chunks = retrieve_chunks(
        question_embedding=question_embedding,
        subject=subject,
        top_k=5
    )

    prompt = build_prompt(question, context_chunks)
    return ask_gigachat(prompt)
