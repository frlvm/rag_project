from gigachat import GigaChat
from django.conf import settings


def get_gigachat_client():
    return GigaChat(
        credentials=settings.GIGACHAT_CREDENTIALS,
        scope="GIGACHAT_API_PERS",
        verify_ssl_certs=False,  # важно для локальной разработки
    )


def ask_gigachat(prompt: str) -> str:
    giga = get_gigachat_client()
    response = giga.chat(prompt)
    return response.choices[0].message.content
