FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/llm ./src/llm
COPY src/common ./src/common

ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["uvicorn", "src.llm.inference.server:app", "--host", "0.0.0.0", "--port", "8001"]
