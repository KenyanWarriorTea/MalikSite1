#!/bin/sh
set -e

python - <<'PY'
from pathlib import Path

p = Path('judge0_client.py')
s = p.read_text()

# Judge0 CE exposes /system_info reliably, while /health may be unavailable.
s = s.replace('/health', '/system_info')

# The app stores memory in MB, Judge0 expects KB.
s = s.replace(
    '"memory_limit": memory_limit,',
    '"memory_limit": int(memory_limit) * 1024 if int(memory_limit) < 1024 else int(memory_limit),'
)

# Judge0 can return null stdout/stderr for internal errors. Do not crash the web app.
s = s.replace(
    'actual_output = result.get("stdout", "").strip()',
    'actual_output = str(result.get("stdout") or "").strip()'
)
s = s.replace(
    'expected_output_stripped = expected_output.strip()',
    'expected_output_stripped = str(expected_output or "").strip()'
)
s = s.replace(
    '"stdout": data.get("stdout", ""),',
    '"stdout": data.get("stdout") or "",'
)
s = s.replace(
    '"stderr": data.get("stderr", ""),',
    '"stderr": data.get("stderr") or "",'
)
s = s.replace(
    '"compile_output": data.get("compile_output", ""),',
    '"compile_output": data.get("compile_output") or data.get("message") or "",'
)

p.write_text(s)
PY

exec uvicorn app:app --host 0.0.0.0 --port 8000
