"""Judge0 API integration for code evaluation"""
import os
import requests
import time
import logging
from typing import Optional, Dict, Any
from models import SubmissionStatus

JUDGE0_URL = os.getenv("JUDGE0_URL", "http://judge0:2358")
JUDGE0_REQUEST_TIMEOUT = 10  # seconds - timeout for individual HTTP requests
JUDGE0_POLLING_TIMEOUT = 30  # seconds - total timeout for polling
JUDGE0_HEALTH_TIMEOUT = 5  # seconds - timeout for health check

logger = logging.getLogger(__name__)



def check_judge0_health() -> bool:
    """
    Check if Judge0 is accessible and healthy.
    Returns True if Judge0 is running, False otherwise.
    """
    try:
        url = f"{JUDGE0_URL}/health"
        response = requests.get(url, timeout=JUDGE0_HEALTH_TIMEOUT)
        is_healthy = response.status_code == 200
        if is_healthy:
            logger.debug("Judge0 health check passed")
        else:
            logger.warning(f"Judge0 health check failed with status {response.status_code}")
        return is_healthy
    except Exception as e:
        logger.error(f"Judge0 health check failed: {e}")
        return False


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
        
        response = requests.post(url, json=payload, timeout=JUDGE0_REQUEST_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        token = data.get("token")
        if token:
            logger.debug(f"Successfully submitted code to Judge0, token: {token}")
        else:
            logger.warning(f"No token in Judge0 response: {data}")
        return token
    except Exception as e:
        logger.error(f"Error submitting code to Judge0: {e}")
        return None




def get_judge0_result(token: str) -> Dict[str, Any]:
    """
    Get the result of a Judge0 submission by token.
    Returns dict with status, stdout, stderr, etc.
    
    Handles both API response formats:
    - status as nested object: {"status": {"id": 3, "description": "Accepted"}}
    - status as integer: {"status": 3}
    """
    try:
        url = f"{JUDGE0_URL}/submissions/{token}?base64=false"
        response = requests.get(url, timeout=JUDGE0_REQUEST_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        logger.debug(f"Judge0 response for token {token}: {data}")
        
        # Handle both possible response formats for status
        status_id = None
        status_desc = "Unknown"
        
        status_obj = data.get("status")
        if isinstance(status_obj, dict):
            # Status is an object: {"id": 3, "description": "Accepted"}
            status_id = status_obj.get("id")
            status_desc = status_obj.get("description", "Unknown")
        elif isinstance(status_obj, int):
            # Status is an integer: 3
            status_id = status_obj
            # Description will be determined by map_judge0_status
            status_desc = "Unknown"
        
        return {
            "status_id": status_id,
            "status_desc": status_desc,
            "stdout": data.get("stdout", ""),
            "stderr": data.get("stderr", ""),
            "time": data.get("time", "0"),
            "memory": data.get("memory", "0"),
            "compile_output": data.get("compile_output", ""),
        }
    except Exception as e:
        logger.error(f"Error getting Judge0 result for token {token}: {e}")
        return {}




def wait_for_judge0_result(
    token: str,
    max_wait: int = 30,
    poll_interval: float = 0.5,
) -> Dict[str, Any]:
    """
    Poll Judge0 until submission is complete.
    Returns the result or empty dict if timeout.
    
    Status IDs: 1=In Queue, 2=Processing, 3=Accepted, 4=Wrong Answer, etc.
    """
    start_time = time.time()
    poll_count = 0
    
    while time.time() - start_time < max_wait:
        result = get_judge0_result(token)
        poll_count += 1
        
        # Check if we got a valid response
        if result:
            status_id = result.get("status_id")
            
            # If status_id is None, the API didn't return a status yet
            if status_id is None:
                logger.debug(f"Poll #{poll_count}: No status_id yet, continuing...")
                time.sleep(poll_interval)
                continue
            
            # Status IDs 1 and 2 mean still processing
            if status_id not in [1, 2]:
                logger.info(f"Poll #{poll_count}: Got final status {status_id}")
                return result
            
            logger.debug(f"Poll #{poll_count}: Still processing (status {status_id})")
        else:
            logger.debug(f"Poll #{poll_count}: Empty response from Judge0, retrying...")
        
        time.sleep(poll_interval)
    
    logger.warning(f"Polling timeout after {poll_count} attempts and {max_wait}s")
    return {}



def stream_judge0_result(
    token: str,
    max_wait: int = 30,
    poll_interval: float = 0.5,
):
    """
    Stream Judge0 submission results in real-time.
    Yields updates as the submission progresses through compilation and execution.
    Yields dict with keys: status_id, compile_output, stdout, stderr, time, memory
    """
    start_time = time.time()
    poll_count = 0
    last_compile_output = ""
    last_stdout = ""
    last_stderr = ""
    
    while time.time() - start_time < max_wait:
        result = get_judge0_result(token)
        poll_count += 1
        
        # Check if we got a valid response
        if result:
            status_id = result.get("status_id")
            
            # If status_id is None, the API didn't return a status yet
            if status_id is None:
                logger.debug(f"Stream poll #{poll_count}: No status_id yet, continuing...")
                time.sleep(poll_interval)
                continue
            
            # Yield any new output that appeared
            current_compile_output = result.get("compile_output", "")
            current_stdout = result.get("stdout", "")
            current_stderr = result.get("stderr", "")
            
            has_new_output = (
                current_compile_output != last_compile_output or
                current_stdout != last_stdout or
                current_stderr != last_stderr or
                status_id not in [1, 2]  # Status changed
            )
            
            if has_new_output:
                logger.debug(f"Stream poll #{poll_count}: Status {status_id}, yielding update")
                yield {
                    "status_id": status_id,
                    "compile_output": current_compile_output,
                    "stdout": current_stdout,
                    "stderr": current_stderr,
                    "time": result.get("time", "0"),
                    "memory": result.get("memory", "0"),
                    "complete": status_id not in [1, 2],
                }
                
                last_compile_output = current_compile_output
                last_stdout = current_stdout
                last_stderr = current_stderr
                
                # If submission is complete, stop streaming
                if status_id not in [1, 2]:
                    logger.info(f"Stream complete: Poll #{poll_count}, status {status_id}")
                    return
            
            logger.debug(f"Stream poll #{poll_count}: Status {status_id}, no new output")
        else:
            logger.debug(f"Stream poll #{poll_count}: Empty response from Judge0, retrying...")
        
        time.sleep(poll_interval)
    
    logger.warning(f"Stream timeout after {poll_count} attempts and {max_wait}s")
    return


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
    # Check Judge0 health before submitting
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
        logger.warning(f"Polling timeout for token {token}")
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
            "test_results": [],
            "token": None,
        }
    
    test_results = []
    tests_passed = 0
    failed_test_number = None
    overall_status = "Accepted"
    token = None  # Will store the first token for streaming
    
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
        
        # Store the first token
        if token is None and result.get("token"):
            token = result.get("token")
        
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
            "token": result.get("token"),  # Store token per test
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
        "test_results": test_results,
        "token": token,  # Return first token for streaming
    }
