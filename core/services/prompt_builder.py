NO_RELEVANT_INFO_ANSWER = "В предоставленных документах нет информации об этом"


def build_prompt(documents, metadatas, question):
    if not documents:
        return NO_RELEVANT_INFO_ANSWER

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
Ты — система ответов строго по предоставленным документам.

Правила:
1. Отвечай только на основании материалов ниже.
2. Не используй внешние знания, предположения и примерные расчеты.
3. Не придумывай исходные данные, числа, даты, цены, названия и факты.
4. Если в материалах нет прямого ответа на вопрос, ответь ровно так:
{NO_RELEVANT_INFO_ANSWER}
5. Если ответа нет, не объясняй возможные причины и не предлагай расчет.
6. Не указывай источники в тексте ответа: приложение добавит их отдельно.

Материалы:
{context}

Вопрос:
{question}
"""
