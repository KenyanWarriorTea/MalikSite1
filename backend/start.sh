#!/bin/sh
set -e

python - <<'PY'
from pathlib import Path

p = Path('judge0_client.py')
s = p.read_text()

# Judge0 CE exposes /system_info reliably, while /health may be unavailable.
s = s.replace('/health', '/system_info')

# Judge0 CE 1.13 is more stable when submission source/stdin/expected_output
# are sent as base64. Results are still fetched decoded with base64_encoded=false.
s = s.replace('import requests', 'import requests\nimport base64')
s = s.replace(
    'url = f"{JUDGE0_URL}/submissions"',
    'url = f"{JUDGE0_URL}/submissions?base64_encoded=true&wait=false"'
)
s = s.replace('?base64=false', '?base64_encoded=false')
s = s.replace(
    '"source_code": source_code,',
    '"source_code": base64.b64encode(str(source_code or "").encode()).decode(),'
)
s = s.replace(
    '"expected_output": expected_output,',
    '"expected_output": base64.b64encode(str(expected_output or "").encode()).decode(),'
)
s = s.replace(
    '"stdin": stdin,',
    '"stdin": base64.b64encode(str(stdin or "").encode()).decode(),'
)

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
