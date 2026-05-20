import json
import os
import random
from pathlib import Path

from locust import between, task
from locust.exception import StopUser

from locust_load_scenarios import (
    BASE_DIR,
    DjangoSessionUser,
    _pick_account,
    _read_env_credentials,
    _read_paths,
)


DEFAULT_RAG_QUESTION = (
    "Чем защитное заземление отличается от рабочего заземления и заземления "
    "молниезащиты, и за счёт чего защитное заземление снижает напряжение "
    "прикосновения и шага?"
)
DEFAULT_RAG_QUESTIONS = "|".join([
    DEFAULT_RAG_QUESTION,
    "От каких параметров зависит электрическое сопротивление тела человека?",
    "Какие измерения выполняются при оценке эффективности защитного заземления в системе IT?",
    "Для чего применяется зануление и как проверяется работа автоматической защиты?",
    "Как выполняется искусственное дыхание и закрытый массаж сердца при оказании первой помощи?",
])
MODEL_ERROR_TEXT = "Произошла ошибка при обработке запроса."


def _read_questions(name="LOCUST_NG_QUESTIONS"):
    raw_value = os.getenv(name, DEFAULT_RAG_QUESTIONS)
    return [item.strip() for item in raw_value.split("|") if item.strip()]


def _read_ids(name, default="9"):
    raw_value = os.getenv(name, default).strip()
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _pick_from_list(values, environment, attr_name):
    if not values:
        return None

    index = getattr(environment, attr_name, 0)
    value = values[index % len(values)]
    setattr(environment, attr_name, index + 1)
    return value


class RAGStudentScenarioUser(DjangoSessionUser):
    abstract = True
    wait_time = between(0.5, 1.5)
    student_accounts = _read_env_credentials("LOCUST_STUDENT_USERS")
    questions = _read_questions()
    expected_source = os.getenv("LOCUST_NG_EXPECTED_SOURCE", "large").strip()

    def get_account(self):
        return _pick_account(self.student_accounts, self.environment)

    def open_chat_page(self, subject_id, name):
        with self.client.get(
            f"/chat/{subject_id}/",
            name=name,
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Chat page is unavailable")
            if (
                response.status_code == 200
                and self.expected_source
                and self.expected_source not in response.text
            ):
                response.failure(
                    f"Expected source document marker '{self.expected_source}' was not found on chat page"
                )

    def send_rag_question(self, subject_id, question, name):
        self.open_chat_page(subject_id, f"{name}: GET chat page")

        csrf_token = self.client.cookies.get("csrftoken")
        if not csrf_token:
            raise ValueError("Could not obtain csrftoken before sending a question")

        with self.client.post(
            f"/chat/{subject_id}/send/",
            data=json.dumps({"question": question}),
            headers={
                "Content-Type": "application/json",
                "X-CSRFToken": csrf_token,
                "Referer": f"{self.host}/chat/{subject_id}/",
            },
            name=name,
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "RAG question request failed")
            if response.status_code != 200:
                return

            try:
                payload = response.json()
            except ValueError:
                response.failure("RAG response is not valid JSON")
                return

            answer = payload.get("answer", {})
            answer_text = answer.get("message", "")
            if not payload.get("success"):
                response.failure(f"RAG response success flag is false: {payload}")
            elif not answer_text:
                response.failure(f"RAG answer was not returned: {payload}")
            elif MODEL_ERROR_TEXT in answer_text:
                response.failure(f"External model/RAG error was returned: {answer_text}")

            sources = answer.get("sources") or payload.get("sources")
            if sources is not None and not sources:
                response.failure("Sources field exists but is empty")


class NG01SingleIndexedDocumentRequest(RAGStudentScenarioUser):
    """
    НГ-01. Одиночный запрос как базовый замер.

    Рекомендуемый запуск:
    locust -f tests/locust/locustfile.py NG01SingleIndexedDocumentRequest --headless -u 1 -r 1 -t 1m
    """

    fixed_count = 1
    subject_id = os.getenv("LOCUST_NG_SUBJECT_ID", "9").strip()

    @task
    def single_question(self):
        self.send_rag_question(
            self.subject_id,
            self.questions[0],
            "NG-01 single indexed document question",
        )
        raise StopUser()


class NG02FiveUsersSameSubject(RAGStudentScenarioUser):
    """
    НГ-02. До 5 параллельных запросов к одному предмету.

    Рекомендуемый запуск: -u 5 -r 5.
    """

    subject_id = os.getenv("LOCUST_NG_SUBJECT_ID", "9").strip()

    @task
    def ask_same_subject(self):
        self.send_rag_question(
            self.subject_id,
            random.choice(self.questions),
            "NG-02 same subject concurrent question",
        )


class NG03FiveUsersDifferentSubjects(RAGStudentScenarioUser):
    """
    НГ-03. До 5 параллельных запросов к разным предметам.

    Задай список предметов через LOCUST_NG_SUBJECT_IDS=9,10,11,12,13.
    """

    subject_ids = _read_ids("LOCUST_NG_SUBJECT_IDS", default="9")

    def on_start(self):
        super().on_start()
        self.subject_id = _pick_from_list(
            self.subject_ids,
            self.environment,
            "_ng03_subject_index",
        )

    @task
    def ask_different_subject(self):
        self.send_rag_question(
            self.subject_id,
            random.choice(self.questions),
            "NG-03 different subjects question",
        )


class NG04GigaChatQueue(RAGStudentScenarioUser):
    """
    НГ-04. Очередь обращений к GigaChat.

    В приложении обращения к GigaChat сериализуются через gigachat_lock.
    Для проверки журнала смотри события gigachat_lock_acquired в logs/rag.log.
    Рекомендуемый запуск: -u 5 -r 5.
    """

    subject_id = os.getenv("LOCUST_NG_SUBJECT_ID", "9").strip()

    @task
    def queued_model_request(self):
        self.send_rag_question(
            self.subject_id,
            random.choice(self.questions),
            "NG-04 queued GigaChat request",
        )


class NG05MaxDocumentsSearch(RAGStudentScenarioUser):
    """
    НГ-05. Поиск при максимальном количестве документов.

    Перед запуском нужно заранее проиндексировать до 200 документов в выбранном предмете.
    LOCUST_NG_MAX_DOC_SUBJECT_ID по умолчанию равен 9.
    """

    subject_id = os.getenv("LOCUST_NG_MAX_DOC_SUBJECT_ID", "7").strip()

    @task
    def ask_subject_with_many_documents(self):
        self.send_rag_question(
            self.subject_id,
            random.choice(self.questions),
            "NG-05 max documents subject question",
        )


class NG06TeacherMaterialsUser(DjangoSessionUser):
    teacher_accounts = _read_env_credentials("LOCUST_TEACHER_USERS")
    subject_id = os.getenv("LOCUST_NG_TEACHER_SUBJECT_ID", "7").strip()
    upload_files = _read_paths("LOCUST_NG_UPLOAD_FILES")
    upload_enabled = os.getenv("LOCUST_NG_UPLOAD", "0").strip() == "1"
    wait_time = between(1, 2)

    def get_account(self):
        return _pick_account(self.teacher_accounts, self.environment)

    @task(3)
    def open_materials(self):
        with self.client.get(
            f"/teacher/subject/{self.subject_id}/",
            name="NG-06 teacher open materials",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Teacher materials page is unavailable")

    @task(1)
    def upload_material(self):
        if not self.upload_enabled or not self.upload_files:
            return

        file_path = random.choice(self.upload_files)
        if not file_path.is_absolute():
            file_path = BASE_DIR / file_path
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Upload file not found: {file_path}")

        with self.client.get(
            f"/teacher/subject/{self.subject_id}/",
            name="NG-06 teacher csrf before upload",
            catch_response=True,
        ) as subject_page:
            self.assert_status(subject_page, {200}, "Subject page is unavailable before upload")

        csrf_token = self.client.cookies.get("csrftoken")
        if not csrf_token:
            raise ValueError("Could not obtain csrftoken before upload")

        with Path(file_path).open("rb") as uploaded_file:
            with self.client.post(
                f"/teacher/subject/{self.subject_id}/",
                data={"csrfmiddlewaretoken": csrf_token},
                files={"file": (Path(file_path).name, uploaded_file)},
                headers={"Referer": f"{self.host}/teacher/subject/{self.subject_id}/"},
                allow_redirects=False,
                name="NG-06 teacher upload material",
                catch_response=True,
            ) as response:
                self.assert_status(response, self.expected_redirects, "Teacher upload did not redirect")


class NG06StudentChatUser(RAGStudentScenarioUser):
    subject_id = os.getenv("LOCUST_NG_SUBJECT_ID", "7").strip()
    wait_time = between(1, 2)

    @task
    def ask_while_teacher_works(self):
        self.send_rag_question(
            self.subject_id,
            random.choice(self.questions),
            "NG-06 student question while teacher works",
        )
