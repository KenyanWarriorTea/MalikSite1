"""Code evaluation helpers.

Judge0 is kept as a fallback for non-Python languages. Python submissions are
executed locally inside the backend container because Judge0/isolate can fail on
some Windows Docker Desktop setups with `/box/script.py` sandbox errors.
"""
import base64
import logging
import os
import subprocess
import sys
import time
from typing import Optional, Dict, Any

import requests

from models import SubmissionStatus

JUDGE0_URL = os.getenv("JUDGE0_URL", "http://judge0:2358")
JUDGE0_REQUEST_TIMEOUT = 10
JUDGE0_POLLING_TIMEOUT = 30
JUDGE0_HEALTH_TIMEOUT = 5
PYTHON_LANGUAGE_IDS = {34, 35, 36, 37, 70, 71}

logger = logging.getLogger(__name__)


def check_judge0_health() -> bool:
    """Return True when Judge0 responds to a lightweight endpoint."""
    for endpoint in ("/system_info", "/languages"):
        try:
            response = requests.get(f"{JUDGE0_URL}{endpoint}", timeout=JUDGE0_HEALTH_TIMEOUT)
            if 200 <= response.status_code < 500:
                return True
            logger.warning("Judge0 health check %s returned %s", endpoint, response.status_code)
        except Exception as exc:
            logger.warning("Judge0 health check %s failed: %s", endpoint, exc)
    return False


def _to_b64(value: str) -> str:
    return base64.b64encode(str(value or "").encode("utf-8")).decode("ascii")


def submit_code_to_judge0(
    source_code: str,
    language_id: int,
    expected_output: str = "",
    stdin: str = "",
    time_limit: int = 2,
    memory_limit: int = 256,
) -> Optional[str]:
    """Submit code to Judge0 and return the submission token."""
    try:
        url = f"{JUDGE0_URL}/submissions?base64_encoded=true&wait=false"
        memory_kb = int(memory_limit) * 1024 if int(memory_limit) < 1024 else int(memory_limit)
        payload = {
            "language_id": int(language_id),
            "source_code": _to_b64(source_code),
            "expected_output": _to_b64(expected_output),
            "stdin": _to_b64(stdin),
            "cpu_time_limit": int(time_limit),
            "memory_limit": memory_kb,
        }
        response = requests.post(url, json=payload, timeout=JUDGE0_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        token = data.get("token")
        if not token:
            logger.warning("No token in Judge0 response: %s", data)
        return token
    except Exception as exc:
        logger.error("Error submitting code to Judge0: %s", exc)
        return None


def get_judge0_result(token: str) -> Dict[str, Any]:
    """Fetch a Judge0 result by token."""
    try:
        url = f"{JUDGE0_URL}/submissions/{token}?base64_encoded=false"
        response = requests.get(url, timeout=JUDGE0_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        status_id = None
        status_desc = "Unknown"
        status_obj = data.get("status")
        if isinstance(status_obj, dict):
            status_id = status_obj.get("id")
            status_desc = status_obj.get("description", "Unknown")
        elif isinstance(status_obj, int):
            status_id = status_obj

        return {
            "status_id": status_id,
            "status_desc": status_desc,
            "stdout": data.get("stdout") or "",
            "stderr": data.get("stderr") or "",
            "time": data.get("time") or "0",
            "memory": data.get("memory") or "0",
            "compile_output": data.get("compile_output") or data.get("message") or "",
        }
    except Exception as exc:
        logger.error("Error getting Judge0 result for token %s: %s", token, exc)
        return {}


def wait_for_judge0_result(token: str, max_wait: int = 30, poll_interval: float = 0.5) -> Dict[str, Any]:
    """Poll Judge0 until the submission is complete."""
    start_time = time.time()
    poll_count = 0
    while time.time() - start_time < max_wait:
        result = get_judge0_result(token)
        poll_count += 1
        if result:
            status_id = result.get("status_id")
            if status_id is None:
                time.sleep(poll_interval)
                continue
            if status_id not in [1, 2]:
                logger.info("Poll #%s: Got final status %s", poll_count, status_id)
                return result
        time.sleep(poll_interval)
    logger.warning("Polling timeout after %s attempts and %ss", poll_count, max_wait)
    return {}


def stream_judge0_result(token: str, max_wait: int = 30, poll_interval: float = 0.5):
    """Yield Judge0 result updates for SSE streaming."""
    start_time = time.time()
    last_payload = None
    while time.time() - start_time < max_wait:
        result = get_judge0_result(token)
        if result:
            status_id = result.get("status_id")
            if status_id is not None:
                payload = {
                    "status_id": status_id,
                    "compile_output": result.get("compile_output", ""),
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "time": result.get("time", "0"),
                    "memory": result.get("memory", "0"),
                    "complete": status_id not in [1, 2],
                }
                if payload != last_payload:
                    yield payload
                    last_payload = payload
                if payload["complete"]:
                    return
        time.sleep(poll_interval)


def map_judge0_status(status_id: Optional[int], status_desc: str = "") -> str:
    """Map Judge0 status ID to the app status enum."""
    status_map = {
        1: SubmissionStatus.PENDING.value,
        2: SubmissionStatus.EVALUATING.value,
        3: SubmissionStatus.ACCEPTED.value,
        4: SubmissionStatus.WRONG_ANSWER.value,
        5: SubmissionStatus.TIME_LIMIT_EXCEEDED.value,
        6: SubmissionStatus.COMPILATION_ERROR.value,
        7: SubmissionStatus.RUNTIME_ERROR.value,
        8: SubmissionStatus.RUNTIME_ERROR.value,
        9: SubmissionStatus.RUNTIME_ERROR.value,
        10: SubmissionStatus.RUNTIME_ERROR.value,
        11: SubmissionStatus.RUNTIME_ERROR.value,
        12: SubmissionStatus.RUNTIME_ERROR.value,
        13: SubmissionStatus.ERROR.value,
        14: SubmissionStatus.ERROR.value,
    }
    return status_map.get(status_id, SubmissionStatus.ERROR.value)


def evaluate_python_locally(
    source_code: str,
    stdin: str = "",
    time_limit: int = 2,
    memory_limit: int = 256,
) -> Dict[str, Any]:
    """Evaluate a Python submission inside the backend container."""
    start = time.time()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", str(source_code or "")],
            input=str(stdin or ""),
            text=True,
            capture_output=True,
            timeout=max(1, int(time_limit)),
        )
        elapsed = round(time.time() - start, 3)
        if completed.returncode == 0:
            status = SubmissionStatus.ACCEPTED.value
        else:
            status = SubmissionStatus.RUNTIME_ERROR.value
        return {
            "status": status,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
            "compile_output": "",
            "token": None,
            "time": str(elapsed),
            "memory": "0",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": SubmissionStatus.TIME_LIMIT_EXCEEDED.value,
            "stdout": exc.stdout or "",
            "stderr": "Time limit exceeded",
            "compile_output": "",
            "token": None,
            "time": str(time_limit),
            "memory": "0",
        }
    except Exception as exc:
        return {
            "status": SubmissionStatus.ERROR.value,
            "stdout": "",
            "stderr": str(exc),
            "compile_output": "",
            "token": None,
            "time": "0",
            "memory": "0",
        }


def evaluate_submission(
    source_code: str,
    language_id: int,
    expected_output: str = "",
    stdin: str = "",
    time_limit: int = 2,
    memory_limit: int = 256,
) -> Dict[str, Any]:
    """Evaluate code using local Python execution or Judge0 fallback."""
    if int(language_id) in PYTHON_LANGUAGE_IDS:
        return evaluate_python_locally(source_code, stdin, time_limit, memory_limit)

    if not check_judge0_health():
        logger.error("Judge0 is not healthy, cannot evaluate submission")
        return {
            "status": SubmissionStatus.ERROR.value,
            "stdout": "",
            "stderr": "Judge0 service is unavailable",
            "token": None,
        }

    token = submit_code_to_judge0(source_code, language_id, expected_output, stdin, time_limit, memory_limit)
    if not token:
        return {
            "status": SubmissionStatus.ERROR.value,
            "stdout": "",
            "stderr": "Failed to submit code to Judge0",
            "token": None,
        }

    result = wait_for_judge0_result(token, max_wait=JUDGE0_POLLING_TIMEOUT)
    if not result:
        return {
            "status": SubmissionStatus.EVALUATING.value,
            "stdout": "",
            "stderr": "Evaluation timeout - still processing",
            "token": token,
        }

    status = map_judge0_status(result.get("status_id"), result.get("status_desc", ""))
    return {
        "status": status,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "compile_output": result.get("compile_output", ""),
        "token": token,
        "time": result.get("time", "0"),
        "memory": result.get("memory", "0"),
    }


def compare_outputs(actual: str, expected: str) -> bool:
    """Compare output values while ignoring trailing whitespace."""
    actual = str(actual or "")
    expected = str(expected or "")
    return actual.strip() == expected.strip()


def evaluate_code_with_tests(
    source_code: str,
    language_id: int,
    tests: list,
    time_limit: int = 2,
    memory_limit: int = 256,
) -> Dict[str, Any]:
    """Evaluate code against multiple tests."""
    logger.info("evaluate_code_with_tests called: tests_count=%s language_id=%s", len(tests or []), language_id)
    if not tests:
        return {
            "verdict": "No tests",
            "details": "No tests configured for this assignment. Ask your teacher to add at least one test (input + expected output) and republish the assignment.",
            "tests_passed": 0,
            "total_tests": 0,
            "failed_test_number": None,
            "test_results": [],
            "token": None,
        }

    test_results = []
    tests_passed = 0
    failed_test_number = None
    overall_status = SubmissionStatus.ACCEPTED.value
    token = None

    for test_num, test in enumerate(tests, 1):
        test_input = str(test.get("input", ""))
        expected_output = str(test.get("expected_output", ""))
        result = evaluate_submission(
            source_code=source_code,
            language_id=language_id,
            expected_output=expected_output,
            stdin=test_input,
            time_limit=time_limit,
            memory_limit=memory_limit,
        )

        if token is None and result.get("token"):
            token = result.get("token")

        actual_output = str(result.get("stdout") or "").strip()
        expected_output_stripped = expected_output.strip()
        test_result = {
            "test_number": test_num,
            "status": result.get("status", SubmissionStatus.ERROR.value),
            "input": test_input,
            "expected_output": expected_output,
            "actual_output": actual_output,
            "stderr": result.get("stderr") or result.get("compile_output") or "",
            "time": result.get("time", "0"),
            "memory": result.get("memory", "0"),
            "token": result.get("token"),
        }

        if result.get("status") == SubmissionStatus.ACCEPTED.value and compare_outputs(actual_output, expected_output_stripped):
            test_result["passed"] = True
            tests_passed += 1
        else:
            test_result["passed"] = False
            failed_test_number = test_num
            if result.get("status") == SubmissionStatus.ACCEPTED.value:
                overall_status = f"Wrong Answer on test {test_num}"
            else:
                overall_status = result.get("status", SubmissionStatus.ERROR.value)
            test_results.append(test_result)
            break

        test_results.append(test_result)

    if tests_passed == len(tests):
        overall_status = SubmissionStatus.ACCEPTED.value

    return {
        "verdict": overall_status,
        "details": overall_status,
        "tests_passed": tests_passed,
        "total_tests": len(tests),
        "failed_test_number": failed_test_number,
        "test_results": test_results,
        "token": token,
    }
