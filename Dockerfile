FROM python:3.12
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD [ "gunicorn", "rag_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1" ]
