import json
import logging
from contextlib import contextmanager
from time import perf_counter


def _serialize_fields(fields):
    return json.dumps(fields, ensure_ascii=False, default=str, sort_keys=True)


def log_event(logger, level, event, **fields):
    logger.log(level, "%s | %s", event, _serialize_fields(fields))


def _short_text(value, limit=140):
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def print_document_upload_event(document, first_chunk, last_chunk, chunk_count, unit_count, duration_ms):
    subject = document.subject
    teacher = subject.teacher
    file_size = document.file.size if document.file else 0

    print()
    print("Событие: загрузка документа")
    print("Данные о документе:")
    print(f"- ID документа: {document.id}")
    print(f"- Название файла: {document.title}")
    print(f"- Размер файла: {file_size} байт")
    print(f"- Предмет: {subject.name} (ID: {subject.id})")
    print(f"- Преподаватель: {teacher.full_name}")
    print(f"- Количество текстовых блоков: {unit_count}")
    print(f"- Количество добавленных чанков: {chunk_count}")

    if first_chunk:
        print("Первая запись о добавлении чанка:")
        print(f"- ID чанка: {first_chunk.id}")
        print(f"- Индекс чанка: {first_chunk.chunk_index}")
        print(f"- Начало текста: {_short_text(first_chunk.content)}")

    if last_chunk:
        print("Последняя запись о добавлении чанка:")
        print(f"- ID чанка: {last_chunk.id}")
        print(f"- Индекс чанка: {last_chunk.chunk_index}")
        print(f"- Начало текста: {_short_text(last_chunk.content)}")

    print("Загрузка успешно завершена")
    print(f"Время выполнения события: {duration_ms} мс")
    print()


def print_document_delete_event(
    document_data,
    postgresql_found_ids,
    postgresql_deleted_ids,
    chroma_found_ids,
    chroma_deleted_ids,
    chroma_remaining_ids,
    duration_ms,
):
    print()
    print("Событие: удаление документа")
    print("Данные о документе:")
    print(f"- ID документа: {document_data['document_id']}")
    print(f"- Название файла: {document_data['document_title']}")
    print(f"- Путь к файлу: {document_data['file_path']}")
    print(f"- Размер файла: {document_data['file_size']} байт")
    print(f"- ID предмета: {document_data['subject_id']}")
    print(f"- Предмет: {document_data['subject_name']}")
    print(f"- Преподаватель: {document_data['teacher_name']}")
    print("Удаление связанных чанков:")
    print(f"- ChromaDB: найдены ID чанков: {', '.join(chroma_found_ids) if chroma_found_ids else 'нет'}")
    print(f"- ChromaDB: удалены ID чанков: {', '.join(chroma_deleted_ids) if chroma_deleted_ids else 'нет'}")
    print(f"- ChromaDB: осталось ID чанков после удаления: {', '.join(chroma_remaining_ids) if chroma_remaining_ids else 'нет'}")
    print(f"- PostgreSQL: найдены ID чанков: {', '.join(postgresql_found_ids) if postgresql_found_ids else 'нет'}")
    print(f"- PostgreSQL: удалены ID чанков: {', '.join(postgresql_deleted_ids) if postgresql_deleted_ids else 'нет'}")
    print("Удаление документа успешно завершено")
    print(f"Время выполнения события: {duration_ms} мс")
    print()


def print_rag_question_event(subject, question, metadatas, answer, duration_ms, documents=None):
    documents = documents or []
    teacher = subject.teacher
    chunk_ids = [
        meta.get("chunk_id")
        for meta in metadatas
        if meta.get("chunk_id")
    ]
    document_titles = sorted({
        str(meta.get("document_title"))
        for meta in metadatas
        if meta.get("document_title")
    })
    subject_ids = sorted({
        str(meta.get("subject_id"))
        for meta in metadatas
        if meta.get("subject_id")
    })

    print()
    print("Событие: обработка вопроса к RAG")
    print("Данные о запросе:")
    print(f"- ID предмета: {subject.id}")
    print(f"- Предмет: {subject.name}")
    print(f"- Преподаватель: {teacher.full_name}")
    print(f"- Вопрос: {_short_text(question, limit=180)}")
    print(f"- Количество используемых чанков: {len(metadatas)}")
    print(f"- ID используемых чанков: {', '.join(map(str, chunk_ids)) if chunk_ids else 'нет'}")
    print(f"- Документы среди найденных чанков: {', '.join(document_titles) if document_titles else 'нет'}")
    print(f"- ID предмета в метаданных чанков: {', '.join(subject_ids) if subject_ids else 'нет'}")
    print(f"- Длина ответа: {len(answer) if answer else 0} символов")
    print("Ответ системы:")
    print(answer or "Ответ не сформирован")

    print("Обработка вопроса успешно завершена")
    print(f"Время выполнения события: {duration_ms} мс")
    print()


@contextmanager
def log_timed_event(logger, level, event, **fields):
    started_at = perf_counter()
    log_event(logger, level, f"{event}_started", **fields)

    try:
        yield
    except Exception:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        log_event(
            logger,
            logging.ERROR,
            f"{event}_failed",
            duration_ms=duration_ms,
            **fields,
        )
        logger.exception("%s_exception", event)
        raise
    else:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        log_event(
            logger,
            level,
            f"{event}_finished",
            duration_ms=duration_ms,
            **fields,
        )
