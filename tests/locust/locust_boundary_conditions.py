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


def _read_paths(name):
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return []

    return [Path(item.strip()) for item in raw_value.split("|") if item.strip()]


def _pick_account(accounts, environment):
    if not accounts:
        return None

    user_index = getattr(environment, "_account_index", 0)
    account = accounts[user_index % len(accounts)]
    environment._account_index = user_index + 1
    return account


class DjangoSessionUser(HttpUser):
    abstract = True
    wait_time = between(1, 2)
    login_path = "/login/"
    expected_redirects = (302, 303)

    def on_start(self):
        self.account = self.get_account()
        if self.account:
            self.login()

    def get_account(self):
        raise NotImplementedError

    def login(self):
        with self.client.get(
            self.login_path,
            name="GET /login/",
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
            name="POST /login/ valid credentials",
            catch_response=True,
        ) as response:
            if response.status_code not in self.expected_redirects:
                response.failure(
                    f"Login failed for {self.account['username']} with {response.status_code}"
                )

    def assert_status(self, response, expected_statuses, message):
        if response.status_code not in expected_statuses:
            response.failure(f"{message}: {response.status_code}")


class AnonymousBoundaryUser(HttpUser):
    wait_time = between(1, 2)

    @task(2)
    def open_login_page(self):
        with self.client.get(
            "/login/",
            name="BOUNDARY anonymous: login page",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Login page returned {response.status_code}")

    @task(1)
    def invalid_login(self):
        with self.client.get("/login/", name="BOUNDARY anonymous: csrf before invalid login"):
            pass

        csrf_token = self.client.cookies.get("csrftoken")
        if not csrf_token:
            raise ValueError("Could not obtain csrftoken from /login/")

        with self.client.post(
            "/login/",
            data={
                "username": "missing_user",
                "password": "wrong_password",
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"Referer": f"{self.host}/login/"},
            name="BOUNDARY anonymous: invalid login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Invalid login should stay on form, got {response.status_code}")

    @task(1)
    def protected_pages_redirect_to_login(self):
        path = random.choice([
            "/student/profile/",
            "/teacher/profile/",
        ])

        with self.client.get(
            path,
            allow_redirects=False,
            name="BOUNDARY anonymous: protected page redirect",
            catch_response=True,
        ) as response:
            if response.status_code != 302:
                response.failure(f"Protected page should redirect, got {response.status_code}")


class StudentBoundaryUser(DjangoSessionUser):
    weight = 2
    student_accounts = _read_env_credentials("LOCUST_STUDENT_USERS")
    subject_id = os.getenv("LOCUST_STUDENT_SUBJECT_ID", "").strip()
    teacher_subject_id = os.getenv("LOCUST_TEACHER_SUBJECT_ID", "").strip()
    enable_llm_chat = os.getenv("LOCUST_ENABLE_LLM_CHAT", "0").strip() == "1"

    def get_account(self):
        return _pick_account(self.student_accounts, self.environment)

    @task(3)
    def open_student_profile_with_auto_subjects(self):
        with self.client.get(
            "/student/profile/",
            name="BOUNDARY student: profile",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Student profile is unavailable")

    @task(2)
    def open_assigned_subject_chat(self):
        if not self.subject_id:
            return

        with self.client.get(
            f"/chat/{self.subject_id}/",
            name="BOUNDARY student: assigned chat",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Assigned chat is unavailable")

    @task(1)
    def empty_question_is_rejected(self):
        if not self.subject_id:
            return

        with self.client.get(f"/chat/{self.subject_id}/", name="BOUNDARY student: csrf before empty chat"):
            pass

        csrf_token = self.client.cookies.get("csrftoken")
        if not csrf_token:
            raise ValueError("Could not obtain csrftoken before sending a question")

        with self.client.post(
            f"/chat/{self.subject_id}/send/",
            data=json.dumps({"question": "   "}),
            headers={
                "Content-Type": "application/json",
                "X-CSRFToken": csrf_token,
                "Referer": f"{self.host}/chat/{self.subject_id}/",
            },
            name="BOUNDARY student: empty question",
            catch_response=True,
        ) as response:
            if response.status_code != 400:
                response.failure(f"Empty question should return 400, got {response.status_code}")

    @task(1)
    def long_question_can_be_sent(self):
        if not self.subject_id or not self.enable_llm_chat:
            return

        with self.client.get(f"/chat/{self.subject_id}/", name="BOUNDARY student: csrf before long chat"):
            pass

        csrf_token = self.client.cookies.get("csrftoken")
        if not csrf_token:
            raise ValueError("Could not obtain csrftoken before sending a question")

        question = "Тестовое сообщение. " * 250
        with self.client.post(
            f"/chat/{self.subject_id}/send/",
            data=json.dumps({"question": question}),
            headers={
                "Content-Type": "application/json",
                "X-CSRFToken": csrf_token,
                "Referer": f"{self.host}/chat/{self.subject_id}/",
            },
            name="BOUNDARY student: long question",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Long question request failed")

    @task(1)
    def teacher_page_is_forbidden_for_student(self):
        if not self.teacher_subject_id:
            return

        with self.client.get(
            f"/teacher/subject/{self.teacher_subject_id}/",
            name="BOUNDARY student: teacher page forbidden",
            catch_response=True,
        ) as response:
            self.assert_status(response, {403, 404}, "Teacher page should not be available to student")


class TeacherBoundaryUser(DjangoSessionUser):
    weight = 1
    teacher_accounts = _read_env_credentials("LOCUST_TEACHER_USERS")
    subject_id = os.getenv("LOCUST_TEACHER_SUBJECT_ID", "").strip()
    upload_files = _read_paths("LOCUST_BOUNDARY_UPLOAD_FILES")

    def get_account(self):
        return _pick_account(self.teacher_accounts, self.environment)

    @task(3)
    def open_teacher_profile(self):
        with self.client.get(
            "/teacher/profile/",
            name="BOUNDARY teacher: profile",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Teacher profile is unavailable")

    @task(2)
    def open_subject_materials(self):
        if not self.subject_id:
            return

        with self.client.get(
            f"/teacher/subject/{self.subject_id}/",
            name="BOUNDARY teacher: subject materials",
            catch_response=True,
        ) as response:
            self.assert_status(response, {200}, "Subject materials page is unavailable")

    @task(1)
    def student_chat_is_forbidden_for_teacher(self):
        if not self.subject_id:
            return

        with self.client.get(
            f"/chat/{self.subject_id}/",
            name="BOUNDARY teacher: student chat forbidden",
            catch_response=True,
        ) as response:
            self.assert_status(response, {403, 404}, "Student chat should not be available to teacher")

    @task(1)
    def add_subject_with_empty_name_is_rejected(self):
        with self.client.get("/teacher/subject/add/", name="BOUNDARY teacher: csrf before invalid subject"):
            pass

        csrf_token = self.client.cookies.get("csrftoken")
        if not csrf_token:
            raise ValueError("Could not obtain csrftoken before adding a subject")

        with self.client.post(
            "/teacher/subject/add/",
            data={
                "name": "",
                "course": "",
                "institute": "",
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"Referer": f"{self.host}/teacher/subject/add/"},
            name="BOUNDARY teacher: invalid subject form",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Invalid subject form should stay on page, got {response.status_code}")

    @task(1)
    def upload_boundary_files(self):
        if not self.subject_id or not self.upload_files:
            return

        file_path = random.choice(self.upload_files)
        if not file_path.exists():
            raise FileNotFoundError(f"Upload file not found: {file_path}")

        with self.client.get(
            f"/teacher/subject/{self.subject_id}/",
            name="BOUNDARY teacher: csrf before upload",
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
                name="BOUNDARY teacher: upload file",
                catch_response=True,
            ) as response:
                self.assert_status(response, self.expected_redirects, "Upload did not redirect")
