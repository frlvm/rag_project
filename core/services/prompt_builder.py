def build_prompt(documents, metadatas, question):

    # 🔥 если нет документов — сразу return (без LLM)
    if not documents:
        return """
Ты — система ответов по документам.

Если информации нет — просто ответь:
"В предоставленных документах нет информации об этом"

НЕ добавляй источник.
"""

    chunks = []

    for doc, meta in zip(documents, metadatas):
        title = meta.get("document_title", "Без названия")
        page_start = meta.get("page_start")
        page_end = meta.get("page_end")

        if page_start and page_end and page_start != page_end:
            page_info = f"стр. {page_start}-{page_end}"
        elif page_start:
            page_info = f"стр. {page_start}"
        else:
            page_info = ""

        chunks.append(
            f"Источник: {title}\n"
            f"{page_info}\n"
            f"Текст:\n{doc}"
        )

    context = "\n\n---\n\n".join(chunks)

    return f"""
Ты — система ответов строго по документам.

ПРАВИЛА:
1. Отвечай ТОЛЬКО на основании материалов ниже.
2. Если точного ответа нет — напиши:
   "В предоставленных документах нет информации об этом"
3. Если ответа нет — НЕ указывай источник.
4. Указывай источник ТОЛЬКО если ответ найден в тексте.
5. Не придумывай информацию.

Формат ответа:

ЕСЛИ ответ найден:
Ответ: <краткий точный ответ>
Источник: <название документа>
(Страница: <номер>) — если есть

ЕСЛИ ответа нет:
Ответ: В предоставленных документах нет информации об этом

Материалы:
{context}

Вопрос:
{question}
"""


'''
def build_prompt(documents, metadatas, question):

    chunks = []
    
    if not documents:
        return "В предоставленных документах нет информации об этом"

    for doc, meta in zip(documents, metadatas):
        title = meta.get("document_title", "Без названия")
        page_start = meta.get("page_start")
        page_end = meta.get("page_end")

        if page_start and page_end and page_start != page_end:
            page_info = f"стр. {page_start}-{page_end}"
        elif page_start:
            page_info = f"стр. {page_start}"
        else:
            page_info = ""

        chunks.append(
            f"Источник: {title}\n"
            f"{page_info}\n"
            f"Текст:\n{doc}"
        )
    context = "\n\n---\n\n".join(chunks)

    return f"""
Ты — система ответов строго по документам.

ПРАВИЛА:
1. Отвечай только на основании материалов ниже.
2. Если в материалах нет точного ответа — напиши: "В предоставленных документах нет информации об этом".
3. После каждого ответа обязательно укажи источник и страницу.
4. Если в контексте есть "Источник" и "Страница", используй именно их.
5. Не придумывай информацию и не обобщай сверх текста.

Формат ответа:
Ответ: <краткий точный ответ>
Источник: <название документа>
(Страница: <номер>) — только если есть

Материалы:
{context}

Вопрос:
{question}
"""'''