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
        title = meta.get("document_title")
        page_start = meta.get("page_start")
        page_end = meta.get("page_end")

        if page_start and page_end and page_start != page_end:
            page_info = f"стр. {page_start}-{page_end}"
        elif page_start:
            page_info = f"стр. {page_start}"
        else:
            page_info = ""

        source_header = f"Источник: {title}\n" if title else ""
        page_line = f"{page_info}\n" if page_info else ""

        chunks.append(
            f"{source_header}"
            f"{page_line}"
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
4. Не указывай источники в тексте ответа: приложение добавит их отдельно.
5. Не придумывай информацию.
6. Пиши нормальным русским языком, без канцелярита и обрывочных формулировок.
7. Дай содержательный ответ на 2-4 предложения, а не одно короткое предложение.
8. Не начинай ответ словами вроде "Рассмотрен" или "Представляет собой", если это делает фразу неестественной.
9. Никогда не пиши в источнике "Без названия".

Формат ответа:

ЕСЛИ ответ найден:
Ответ: <понятный ответ на 2-4 предложения>

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
