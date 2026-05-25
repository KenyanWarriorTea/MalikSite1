FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "python -c 'from pathlib import Path; p=Path(\"judge0_client.py\"); s=p.read_text(); p.write_text(s.replace(\"/health\", \"/system_info\"))' && uvicorn app:app --host 0.0.0.0 --port 8000"]
