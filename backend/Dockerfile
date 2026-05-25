FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "python -c 'from pathlib import Path; p=Path(\"judge0_client.py\"); s=p.read_text(); s=s.replace(\"/health\", \"/system_info\"); s=s.replace(\"\\\"memory_limit\\\": memory_limit,\", \"\\\"memory_limit\\\": int(memory_limit) * 1024 if int(memory_limit) < 1024 else int(memory_limit),\"); p.write_text(s)' && uvicorn app:app --host 0.0.0.0 --port 8000"]
