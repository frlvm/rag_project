def build_prompt(question, chunks):
    if not chunks:
        return f"""
В загруженных документах отсутствует информация,
позволяющая ответить на вопрос.

Вопрос:
{question}
"""

    context = "\n\n".join(
        f"Фрагмент {i+1}:\n{chunk.content}"
        for i, chunk in enumerate(chunks)
    )

    return f"""
Ты — интеллектуальный помощник студента.
Отвечай ТОЛЬКО на основе контекста ниже.

Контекст:
{context}

Вопрос:
{question}

Если информации недостаточно — так и сообщи.
"""
