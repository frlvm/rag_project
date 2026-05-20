import logging
from threading import Lock
from time import perf_counter

from gigachat import GigaChat
from django.conf import settings
from .logging_utils import log_event


logger = logging.getLogger("core.rag")
gigachat_lock = Lock()


def get_gigachat_client():
    return GigaChat(
        credentials=settings.GIGACHAT_CREDENTIALS,
        scope="GIGACHAT_API_PERS",
        verify_ssl_certs=False,  # важно для локальной разработки
    )


def ask_gigachat(prompt: str) -> str:
    wait_started_at = perf_counter()

    with gigachat_lock:
        wait_duration_ms = round((perf_counter() - wait_started_at) * 1000, 2)
        log_event(
            logger,
            logging.INFO,
            "gigachat_lock_acquired",
            wait_duration_ms=wait_duration_ms,
            prompt_length=len(prompt),
        )

        request_started_at = perf_counter()
        giga = get_gigachat_client()
        response = giga.chat(prompt)
        request_duration_ms = round((perf_counter() - request_started_at) * 1000, 2)

        log_event(
            logger,
            logging.INFO,
            "gigachat_request_finished",
            request_duration_ms=request_duration_ms,
            prompt_length=len(prompt),
        )

        return response.choices[0].message.content
