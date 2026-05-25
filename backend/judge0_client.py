"""Judge0 API integration for code evaluation"""
import os
import requests
import time
from typing import Optional, Dict, Any
from models import SubmissionStatus

JUDGE0_URL = os.getenv("JUDGE0_URL", "http://judge0:2358")
JUDGE0_TIMEOUT = 30  # seconds


def submit_code_to_judge0(
    source_code: str,
    language_id: int,
    expected_output: str = "",
    stdin: str = "",
    time_limit: int = 2,
    memory_limit: int = 256,
) -> Optional[str]:
    """
    Submit code to Judge0 for evaluation.
    Returns the token for tracking the submission.
    """
    try:
        url = f"{JUDGE0_URL}/submissions"
        payload = {
            "language_id": language_id,
            "source_code": source_code,
            "expected_output": expected_output,
            "stdin": stdin,
            "cpu_time_limit": time_limit,
            "memory_limit": memory_limit,
        }
        
        response = requests.post(url, json=payload, timeout=JUDGE0_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        return data.get("token")
    except Exception as e:
        print(f"Error submitting code to Judge0: {e}")
        return None


def get_judge0_result(token: str) -> Dict[str, Any]:
    """
    Get the result of a Judge0 submission by token.
    Returns dict with status, stdout, stderr, etc.
    """
    try:
        url = f"{JUDGE0_URL}/submissions/{token}?base64=false"
        response = requests.get(url, timeout=JUDGE0_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        return {
            "status_id": data.get("status", {}).get("id"),
            "status_desc": data.get("status", {}).get("description", "Unknown"),
            "stdout": data.get("stdout", ""),
            "stderr": data.get("stderr", ""),
            "time": data.get("time", "0"),
            "memory": data.get("memory", "0"),
            "compile_output": data.get("compile_output", ""),
        }
    except Exception as e:
        print(f"Error getting Judge0 result: {e}")
        return {}


def wait_for_judge0_result(
    token: str,
    max_wait: int = 30,
    poll_interval: float = 0.5,
) -> Dict[str, Any]:
    """
    Poll Judge0 until submission is complete.
    Returns the result or empty dict if timeout.
    """
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        result = get_judge0_result(token)
        
        if result.get("status_id") is not None:
            status_id = result["status_id"]
            # Status IDs: 1=In Queue, 2=Processing, 3=Accepted, 4=Wrong Answer, etc.
            if status_id not in [1, 2]:  # Not in queue or processing
                return result
        
        time.sleep(poll_interval)
    
    return {}


def map_judge0_status(status_id: Optional[int], status_desc: str) -> str:
    """
    Map Judge0 status ID and description to our status enum.
    Judge0 Status codes:
    1 - In Queue
    2 - Processing
    3 - Accepted
    4 - Wrong Answer
    5 - Time Limit Exceeded
    6 - Compilation Error
    7 - Runtime Error (SIGSEGV)
    8 - Runtime Error (SIGXFSZ)
    9 - Runtime Error (SIGFPE)
    10 - Runtime Error (SIGABRT)
    11 - Runtime Error (NZEC)
    12 - Runtime Error (Other)
    13 - Internal Error
    14 - Exec Format Error
    """
    if status_id is None:
        return SubmissionStatus.ERROR.value
    
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


def evaluate_submission(
    source_code: str,
    language_id: int,
    expected_output: str = "",
    stdin: str = "",
    time_limit: int = 2,
    memory_limit: int = 256,
) -> Dict[str, Any]:
    """
    Evaluate code using Judge0 API (real implementation).
    Returns dict with status and output information.
    """
    token = submit_code_to_judge0(source_code, language_id, expected_output, stdin, time_limit, memory_limit)
    
    if not token:
        return {
            "status": SubmissionStatus.ERROR.value,
            "stdout": "",
            "stderr": "Failed to submit code to Judge0",
            "token": None,
        }
    
    result = wait_for_judge0_result(token)
    
    if not result:
        return {
            "status": SubmissionStatus.EVALUATING.value,
            "stdout": "",
            "stderr": "",
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
    """
    Compare actual output with expected output.
    Ignores trailing whitespace differences.
    """
    if not actual or not expected:
        return actual.strip() == expected.strip()
    
    actual_lines = actual.strip().split('\n')
    expected_lines = expected.strip().split('\n')
    
    if len(actual_lines) != len(expected_lines):
        return False
    
    for actual_line, expected_line in zip(actual_lines, expected_lines):
        if actual_line.strip() != expected_line.strip():
            return False
    
    return True


def evaluate_code_with_tests(
    source_code: str,
    language_id: int,
    tests: list,
    time_limit: int = 2,
    memory_limit: int = 256,
) -> Dict[str, Any]:
    """
    Evaluate code against multiple tests.
    tests: list of dicts with 'input' and 'expected_output' keys
    Returns dict with overall verdict and detailed test results.
    """
    if not tests:
        return {
            "verdict": "No tests",
            "tests_passed": 0,
            "total_tests": 0,
            "failed_test_number": None,
            "test_results": []
        }
    
    test_results = []
    tests_passed = 0
    failed_test_number = None
    overall_status = "Accepted"
    
    for test_num, test in enumerate(tests, 1):
        test_input = test.get("input", "")
        expected_output = test.get("expected_output", "")
        
        # Evaluate code for this test
        result = evaluate_submission(
            source_code,
            language_id,
            expected_output,
            test_input,
            time_limit,
            memory_limit
        )
        
        actual_output = result.get("stdout", "").strip()
        expected_output_stripped = expected_output.strip()
        
        test_result = {
            "test_number": test_num,
            "status": result["status"],
            "input": test_input,
            "expected_output": expected_output,
            "actual_output": actual_output,
            "stderr": result.get("stderr", ""),
            "time": result.get("time", "0"),
            "memory": result.get("memory", "0"),
        }
        
        # Check if output matches (only if no errors)
        if result["status"] == SubmissionStatus.ACCEPTED.value:
            if compare_outputs(actual_output, expected_output_stripped):
                test_result["passed"] = True
                tests_passed += 1
            else:
                test_result["passed"] = False
                if failed_test_number is None:
                    failed_test_number = test_num
                    overall_status = f"Wrong Answer on test {test_num}"
        else:
            # Compilation or Runtime Error
            test_result["passed"] = False
            if failed_test_number is None:
                failed_test_number = test_num
                overall_status = result["status"]
        
        test_results.append(test_result)
        
        # Stop on first failure
        if not test_result.get("passed", False):
            break
    
    # If all tests passed, set overall status to Accepted
    if tests_passed == len(tests):
        overall_status = "Accepted"
    
    return {
        "verdict": overall_status,
        "tests_passed": tests_passed,
        "total_tests": len(tests),
        "failed_test_number": failed_test_number,
        "test_results": test_results
    }
