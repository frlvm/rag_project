import json
import os
import random
from pathlib import Path

from dotenv import load_dotenv
from locust import HttpUser, between, task


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _parse_credentials(raw_value):
    credentials = []

    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue

        if ":" not in item:
            raise ValueError(
                "Credentials must use the format username:password,username2:password2"
            )

        username, password = item.split(":", 1)
        credentials.append({
            "username": username.strip(),
            "password": password.strip(),
        })

    return credentials


def _read_env_credentials(name):
    raw_value = os.getenv(name, "").strip()
    return _parse_credentials(raw_value) if raw_value else []


def _read_questions():
    raw_value = os.getenv(
        "LOCUST_LOAD_QUESTIONS",
        "Здравствуйте|Как получить материалы по предмету?|Какие документы доступны?",
    )
    return [item.strip() for item in raw_value.split("|") if item.strip()]


def _read_paths(name):
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return []

    return [Path(item.strip()) for item in raw_value.split("|") if item.strip()]


def _pick_account(accounts, environment):
    if not accounts:
        return None

    runner = getattr(environment, "runner", None)
    worker_index = getattr(runner, "worker_index", 0) if runner else 0
    user_index = getattr(environment, "_account_index", 0)

    account = accounts[(user_index + worker_index) % len(accounts)]
    environment._account_index = user_index + 1
    return account


class DjangoSessionUser(HttpUser):
    abstract = True
    wait_time = between(1, 3)
    login_path = "/login/"
    expected_redirects = (302, 303)

    def on_start(self):
        self.account = self.get_account()
        if not self.account:
            raise ValueError(
                f"{self.__class__.__name__} requires credentials in environment variables."
            )

        self.login()

    def get_account(self):
        raise NotImplementedError

    def login(self):
        with self.client.get(
            self.login_path,
            name="LOAD GET /login/",
            catch_response=True,
        ) as login_page:
            if login_page.status_code != 200:
                login_page.failure(f"Login page returned {login_page.status_code}")
                return

        csrf_token = self.client.cookies.get("csrftoken")
        if not csrf_token:
            raise ValueError("Could not obtain csrftoken from /login/")

        with self.client.post(
            self.login_path,
            data={
                "username": self.account["username"],
                "password": self.account["password"],
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"Referer": f"{self.host}{self.login_path}"},
            allow_redirects=False,
            name="LOAD POST /login/",
            catch_response=True,
        ) as response:
            if response.status_code not in self.expected_redirects:
                response.failure(
                    f"Login failed for {self.account['username']} with {response.status_code}"
                )

    def assert_status(self, response, expected_statuses, message):
        if response.status_code not in expected_statuses:
            response.failure(f"{message}: {response.status_code}")


class StudentLoadUser(DjangoSessionUser):
    weight = int(os.getenv("LOCUST_LOAD_STUDENT_WEIGHT", "4"))
    student_accounts = _read_env_credentials("LOCUST_STUDENT_USERS")
    subject_id = os.getenv("LOCUST_STUDENT_SUBJECT_ID", "").strip()
    questions = _read_questions()
    send_chat_enabled = os.getenv("LOCUST_LOAD_SEND_CHAT", "1").strip() == "1"

    def get_account(self):
        return _pick_account(self.student_accounts, self.environment)

    @task(5)
    def open_student_profile(self):
        with self.client.get(
            "/student/profile/",
            name="LOAD student: profile",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Student profile is unavailable")

    @task(4)
    def open_subject_chat(self):
        if not self.subject_id:
            return

        with self.client.get(
            f"/chat/{self.subject_id}/",
            name="LOAD student: chat page",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Student chat is unavailable")

    @task(1)
    def send_question_to_chat(self):
        if not self.subject_id or not self.send_chat_enabled:
            return

        with self.client.get(
            f"/chat/{self.subject_id}/",
            name="LOAD student: csrf before chat send",
            catch_response=True,
        ) as chat_page:
            self.assert_status(chat_page, {200}, "Student chat is unavailable before send")

        csrf_token = self.client.cookies.get("csrftoken")
        if not csrf_token:
            raise ValueError("Could not obtain csrftoken before sending a question")

        with self.client.post(
            f"/chat/{self.subject_id}/send/",
            data=json.dumps({"question": random.choice(self.questions)}),
            headers={
                "Content-Type": "application/json",
                "X-CSRFToken": csrf_token,
                "Referer": f"{self.host}/chat/{self.subject_id}/",
            },
            name="LOAD student: send chat message",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Chat message request failed")
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    response.failure("Chat response is not valid JSON")
                    return

                answer = payload.get("answer", {})
                if not payload.get("success") or not answer.get("message"):
                    response.failure(f"LLM answer was not returned: {payload}")


class TeacherLoadUser(DjangoSessionUser):
    weight = int(os.getenv("LOCUST_LOAD_TEACHER_WEIGHT", "1"))
    teacher_accounts = _read_env_credentials("LOCUST_TEACHER_USERS")
    subject_id = os.getenv("LOCUST_TEACHER_SUBJECT_ID", "").strip()
    upload_files = _read_paths("LOCUST_LOAD_UPLOAD_FILES")
    upload_enabled = os.getenv("LOCUST_LOAD_UPLOAD", "0").strip() == "1"

    def get_account(self):
        return _pick_account(self.teacher_accounts, self.environment)

    @task(5)
    def open_teacher_profile(self):
        with self.client.get(
            "/teacher/profile/",
            name="LOAD teacher: profile",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Teacher profile is unavailable")

    @task(4)
    def open_subject_materials(self):
        if not self.subject_id:
            return

        with self.client.get(
            f"/teacher/subject/{self.subject_id}/",
            name="LOAD teacher: subject materials",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Subject materials page is unavailable")

    @task(1)
    def upload_document(self):
        if not self.subject_id or not self.upload_enabled or not self.upload_files:
            return

        file_path = random.choice(self.upload_files)
        if not file_path.exists():
            raise FileNotFoundError(f"Upload file not found: {file_path}")

        with self.client.get(
            f"/teacher/subject/{self.subject_id}/",
            name="LOAD teacher: csrf before upload",
            catch_response=True,
        ) as subject_page:
            self.assert_status(subject_page, {200}, "Subject page is unavailable before upload")

        csrf_token = self.client.cookies.get("csrftoken")
        if not csrf_token:
            raise ValueError("Could not obtain csrftoken before upload")

        with file_path.open("rb") as uploaded_file:
            with self.client.post(
                f"/teacher/subject/{self.subject_id}/",
                data={"csrfmiddlewaretoken": csrf_token},
                files={"file": (file_path.name, uploaded_file)},
                headers={"Referer": f"{self.host}/teacher/subject/{self.subject_id}/"},
                allow_redirects=False,
                name="LOAD teacher: upload document",
                catch_response=True,
            ) as response:
                self.assert_status(response, self.expected_redirects, "Document upload did not redirect")
