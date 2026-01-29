def build_prompt(context_chunks, question):
    context = "\n\n".join(context_chunks)
    return f"""
Отвечай строго по материалам.

Материалы:
{context}

Вопрос:
{question}
"""
