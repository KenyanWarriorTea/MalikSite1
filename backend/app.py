"""
MalikSite1 - Judge0 Educational Platform
Web application for teachers to publish assignments and students to submit solutions.
Includes student activity monitoring for academic integrity.
"""
import html
import json
import os
import re
import secrets
from urllib.parse import quote_plus
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Form, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from database import init_db, get_db
from models import User, AccessCode, Assignment, Submission, StudentActivity, SubmissionStatus
from judge0_client import evaluate_submission, evaluate_code_with_tests, stream_judge0_result
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse
import logging

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
init_db()

app = FastAPI(title="MalikSite1")

SESSION_SECRET = secrets.token_urlsafe(32)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Error handling middleware
class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for handling and logging errors"""
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
            return PlainTextResponse(
                "An error occurred. Please try again later.",
                status_code=500
            )

app.add_middleware(ErrorHandlingMiddleware)

# Default access codes. Teachers can change the active values from the dashboard.
DEFAULT_TEACHER_CODE = os.getenv("TEACHER_CODE", "teacher123")
DEFAULT_STUDENT_CODE = os.getenv("STUDENT_CODE", "student123")
ACCESS_CODE_DEFAULTS = {
    "teacher": DEFAULT_TEACHER_CODE,
    "student": DEFAULT_STUDENT_CODE,
}

# UI Styles
UI_STYLES = """
<style>
body { font-family: sans-serif; max-width: 1200px; margin: 40px auto; padding: 20px; line-height: 1.6; background: #f9f9f9; color: #333; }
form { display: flex; flex-direction: column; gap: 12px; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
input, textarea, select { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; box-sizing: border-box; }
textarea { min-height: 100px; }
button { padding: 12px 24px; border: none; border-radius: 8px; color: white; background: #212121; font-weight: bold; font-size: 16px; cursor: pointer; transition: 0.2s; width: fit-content; }
button:hover { background: #444; }
.logout-btn { display: inline-block; padding: 8px 16px; background: #e0e0e0; color: #333; border-radius: 6px; text-decoration: none; font-size: 14px; margin-bottom: 20px; font-weight: bold; }
.logout-btn:hover { background: #ccc; }
.card { background: white; padding: 20px; border-radius: 12px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); list-style: none; }
pre { background: #f1f1f1; padding: 10px; border-radius: 6px; font-family: monospace; overflow-x: auto; max-height: 200px; }
.status-accepted { color: green; font-weight: bold; }
.status-pending { color: orange; font-weight: bold; }
.status-error { color: red; font-weight: bold; }
.status-wrong { color: #ff6b6b; font-weight: bold; }
.activity-log { background: #ffe0e0; padding: 10px; border-radius: 6px; margin-top: 10px; font-size: 12px; max-height: 150px; overflow-y: auto; color: #c00; }
.activity-item { padding: 4px 0; }
.monitoring-indicator { display: inline-block; padding: 4px 8px; background: #ddd; border-radius: 4px; font-size: 12px; margin-left: 10px; }
.monitoring-active { background: #e0ffe0; color: #080; }
.result-success { background: #c8e6c9; border-left: 4px solid #4caf50; padding: 15px; border-radius: 4px; margin: 10px 0; }
.result-error { background: #ffcdd2; border-left: 4px solid #f44336; padding: 15px; border-radius: 4px; margin: 10px 0; }
.result-success::before { content: '✅ '; font-weight: bold; color: #2e7d32; }
.result-error::before { content: '❌ '; font-weight: bold; color: #c62828; }
.code-output { background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 10px; margin: 10px 0; font-family: monospace; white-space: pre-wrap; word-break: break-word; }
h2 { color: #212121; border-bottom: 2px solid #2196F3; padding-bottom: 10px; }
</style>
"""

LANGUAGE_NAME_TO_ID = {
    "python": 71,
    "cpp": 54,
    "java": 62,
    "javascript": 63,
}

LANGUAGE_ID_TO_NAME = {
    71: "Python",
    62: "Java",
    54: "C++",
    63: "JavaScript",
}

# ============================================================================
# Helper Functions
# ============================================================================

def get_or_create_user(db: Session, name: str, role: str) -> User:
    """Get or create a user in the database"""
    user = db.query(User).filter(
        User.name == name,
        User.role == role
    ).first()
    
    if not user:
        user = User(name=name, role=role)
        db.add(user)
        db.commit()
        db.refresh(user)
    
    return user


def get_access_code(db: Session, role: str) -> str:
    """Return the active access code for a role, creating the default if needed."""
    access_code = db.query(AccessCode).filter(AccessCode.role == role).first()
    if access_code:
        return access_code.code

    default_code = ACCESS_CODE_DEFAULTS[role]
    access_code = AccessCode(role=role, code=default_code)
    db.add(access_code)
    db.commit()
    db.refresh(access_code)
    return access_code.code


def update_access_code(db: Session, role: str, code: str, updated_by: int) -> None:
    """Create or update an access code for a role."""
    cleaned_code = code.strip()
    access_code = db.query(AccessCode).filter(AccessCode.role == role).first()
    if access_code:
        access_code.code = cleaned_code
        access_code.updated_by = updated_by
    else:
        access_code = AccessCode(role=role, code=cleaned_code, updated_by=updated_by)
        db.add(access_code)


def validate_access_codes(teacher_code: str, student_code: str) -> tuple[bool, str]:
    """Validate access code form values."""
    teacher_code = teacher_code.strip()
    student_code = student_code.strip()
    if len(teacher_code) < 4 or len(student_code) < 4:
        return False, "Код должен быть не короче 4 символов."
    if len(teacher_code) > 255 or len(student_code) > 255:
        return False, "Код не должен быть длиннее 255 символов."
    if teacher_code == student_code:
        return False, "Коды учителя и ученика должны отличаться."
    return True, ""


def parse_tests_json(raw_tests: str) -> list[dict]:
    """Parse tests JSON from teacher form payload."""
    if not raw_tests or not raw_tests.strip():
        return []

    try:
        parsed = json.loads(raw_tests)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    cleaned = []
    for test in parsed:
        if not isinstance(test, dict):
            continue
        test_input = str(test.get("input", ""))
        expected_output = str(test.get("expected_output", ""))
        cleaned.append({"input": test_input, "expected_output": expected_output})
    return cleaned


def parse_tests_json_with_validation(raw_tests: str) -> tuple[list[dict], bool]:
    """Parse tests JSON and return (tests, is_valid_json)."""
    if not raw_tests or not raw_tests.strip():
        return [], True

    try:
        parsed = json.loads(raw_tests)
    except json.JSONDecodeError:
        return [], False

    if not isinstance(parsed, list):
        return [], False

    cleaned = []
    for test in parsed:
        if not isinstance(test, dict):
            continue
        test_input = str(test.get("input", ""))
        expected_output = str(test.get("expected_output", ""))
        cleaned.append({"input": test_input, "expected_output": expected_output})
    return cleaned, True


def format_status(status: str) -> tuple[str, str]:
    """Return (CSS class, display text) for submission status"""
    status_lower = status.lower()
    if "accepted" in status_lower:
        return "status-accepted", "✓ " + status
    elif "pending" in status_lower or "evaluating" in status_lower:
        return "status-pending", "⏳ " + status
    elif "error" in status_lower or "compilation" in status_lower or "runtime" in status_lower:
        return "status-error", "✗ " + status
    else:
        return "status-wrong", "✗ " + status


def extract_legacy_io_from_description(description: str) -> tuple[str, str]:
    """Extract legacy stdin/expected output hints from assignment description."""
    if not description:
        return "", ""

    normalized = description.replace("\r", "")

    input_match = re.search(
        r"(?:входные\s+данные|input)\s*[:\-]\s*(.+?)(?=(?:ожидаемый\s+вывод|expected\s+output)\s*[:\-]|$)",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    expected_match = re.search(
        r"(?:ожидаемый\s+вывод|expected\s+output)\s*[:\-]\s*(.+)$",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )

    extracted_input = input_match.group(1).strip() if input_match else ""
    extracted_expected = expected_match.group(1).strip() if expected_match else ""

    return extracted_input, extracted_expected


def get_activity_summary(db: Session, submission_id: int) -> dict:
    """Get activity summary for a submission"""
    if not submission_id:
        return {
            "total": 0,
            "focus_lost": 0,
            "tab_hidden": 0,
            "suspicious_count": 0,
            "activities": []
        }
    
    activities = db.query(StudentActivity).filter(
        StudentActivity.submission_id == submission_id
    ).all()
    
    summary = {
        "total": len(activities),
        "focus_lost": sum(1 for a in activities if a.activity_type == "focus_lost"),
        "tab_hidden": sum(1 for a in activities if a.activity_type == "tab_hidden"),
        "suspicious_count": sum(1 for a in activities if a.is_suspicious),
        "activities": activities
    }
    return summary


# ============================================================================
# Routes
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def login_page():
    """Login page for teachers and students"""
    return f"""
    <html><body>{UI_STYLES}
    <div style='max-width: 400px; margin: 100px auto; text-align: center;'>
        <h1>🎓 MalikSite - Образовательная платформа</h1>
        <form method='post' action='/login'>
          <input name='name' placeholder='Ваше имя' required />
          <input type='password' name='access_code' placeholder='Секретный код доступа' required />
          <button type='submit' style='width: 100%;'>Войти</button>
        </form>
    </div>
    </body></html>
    """


@app.post("/login")
def login(request: Request, name: str = Form(...), access_code: str = Form(...), db: Session = Depends(get_db)):
    """Handle login for teachers and students"""
    teacher_code = get_access_code(db, "teacher")
    student_code = get_access_code(db, "student")

    if access_code == teacher_code:
        role = "teacher"
    elif access_code == student_code:
        role = "student"
    else:
        return RedirectResponse(url="/", status_code=303)
    
    # Get or create user in database
    user = get_or_create_user(db, name, role)
    
    # Store in session
    request.session["user_id"] = user.id
    request.session["name"] = user.name
    request.session["role"] = user.role
    
    redirect_url = "/teacher" if role == "teacher" else "/student"
    return RedirectResponse(url=redirect_url, status_code=303)


@app.get("/teacher", response_class=HTMLResponse)
def teacher_page(request: Request, db: Session = Depends(get_db)):
    """Teacher dashboard - view assignments and student submissions"""
    if request.session.get("role") != "teacher":
        return RedirectResponse(url="/")
    
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/")
    
    name = html.escape(request.session.get("name", "Учитель"))
    
    # Get all assignments by this teacher
    assignments = db.query(Assignment).filter(Assignment.teacher_id == user_id).all()
    form_error = request.query_params.get("form_error")
    assignment_saved = request.query_params.get("assignment_saved")
    tests_saved_count = request.query_params.get("tests_saved_count")
    access_codes_updated = request.query_params.get("access_codes_updated")
    access_code_error = request.query_params.get("access_code_error")
    current_teacher_code = html.escape(get_access_code(db, "teacher"))
    current_student_code = html.escape(get_access_code(db, "student"))
    
    assignment_items = []
    for a in assignments:
        submissions = db.query(Submission).filter(Submission.assignment_id == a.id).all()
        
        language_name = LANGUAGE_ID_TO_NAME.get(a.language_id, "Unknown")
        
        # Display reference code
        reference_display = ""
        if a.reference_code:
            reference_display = f"""
            <div style='margin: 15px 0; padding: 15px; background: #f0f8ff; border-radius: 8px; border-left: 4px solid #2196F3;'>
              <h4 style='margin: 0 0 10px 0; color: #1976d2;'>📝 Эталонный код ({language_name}):</h4>
              <pre style='background: white; border: 1px solid #ddd; margin: 0;'>{html.escape(a.reference_code)}</pre>
            </div>
            """
        
        rows = []
        for s in submissions:
            student = db.query(User).filter(User.id == s.student_id).first()
            student_name = html.escape(student.name if student else "Unknown")
            status_class, status_text = format_status(s.status)
            
            # Get activity summary
            activity_summary = get_activity_summary(db, s.id)
            activity_html = ""
            if activity_summary["suspicious_count"] > 0:
                activity_html = f"""
                <div class='activity-log'>
                  <strong>⚠️ Подозрительная активность обнаружена:</strong><br/>
                  • Потеря фокуса: {activity_summary['focus_lost']} раз<br/>
                  • Скрытие вкладки: {activity_summary['tab_hidden']} раз<br/>
                  • Всего событий: {activity_summary['total']}
                </div>
                """
            
            # Show student output
            output_display = ""
            if s.stdout:
                output_display = f"""
                <div style='margin-top: 10px;'>
                  <strong>Вывод программы:</strong>
                  <pre style='background: #fff3cd; border: 1px solid #ffc107; padding: 10px;'>{html.escape(s.stdout)}</pre>
                </div>
                """
            
            rows.append(
                f"<li style='margin-top:10px; padding-bottom: 15px; border-bottom: 1px solid #eee;'>"
                f"<b>{student_name}</b>: "
                f"<span class='{status_class}'>{status_text}</span>"
                f"<strong style='display: block; margin-top: 10px;'>Код:</strong>"
                f"<pre>{html.escape(s.code)}</pre>"
                f"{output_display}"
                f"<small style='color: #666;'>Отправлено: {s.created_at.strftime('%Y-%m-%d %H:%M:%S')}</small>"
                f"{activity_html}"
                f"</li>"
            )
        
        assignment_items.append(
            f"<li class='card'><h3>Задание: {html.escape(a.title)}</h3>"
            f"<p>{html.escape(a.description)}</p>"
            f"<p><strong>Тип:</strong> {'Кодинг' if a.is_code_assignment else 'Текстовое'}</p>"
            f"<p><strong>Язык:</strong> {language_name}</p>"
            f"<p><strong>Лимиты:</strong> {a.time_limit or 2}s / {a.memory_limit or 256}MB</p>"
            f"{reference_display}"
            f"<h4 style='margin-top: 20px;'>Ответы студентов ({len(submissions)}):</h4>"
            f"<ul>{''.join(rows) or '<li>Решений пока нет</li>'}</ul>"
            f"</li>"
        )
    
    form_message = ""
    if access_code_error:
        form_message = (
            "<div class='result-error' style='margin-bottom:16px;'>"
            f"{html.escape(access_code_error)}"
            "</div>"
        )
    elif access_codes_updated == "1":
        form_message = (
            "<div class='result-success' style='margin-bottom:16px;'>"
            "Коды доступа успешно обновлены."
            "</div>"
        )
    elif form_error:
        form_message = (
            "<div class='result-error' style='margin-bottom:16px;'>"
            f"{html.escape(form_error)}"
            "</div>"
        )
    elif assignment_saved == "1":
        tests_count_text = ""
        if tests_saved_count is not None:
            tests_count_text = f" Сохранено тестов: {html.escape(tests_saved_count)}."
        form_message = (
            "<div class='result-success' style='margin-bottom:16px;'>"
            f"Задание успешно опубликовано.{tests_count_text}"
            "</div>"
        )

    return f"""
    <html><body>{UI_STYLES}
    <h1>Панель учителя: {name}</h1>
    <a href='/' class='logout-btn'>Выйти из системы</a>
    {form_message}
    <form method='post' action='/teacher/access-codes' style='margin-bottom: 20px;'>
      <h2>Коды доступа</h2>
      <input name='teacher_code' value='{current_teacher_code}' placeholder='Код доступа для учителя' required minlength='4' maxlength='255' />
      <input name='student_code' value='{current_student_code}' placeholder='Код доступа для ученика' required minlength='4' maxlength='255' />
      <button type='submit'>Сохранить коды</button>
    </form>
    <form method='post' action='/teacher/assignments' id='assignment_form'>
      <h2>Добавить задание</h2>
      <input name='title' placeholder='Название задания' required />
      <textarea name='description' placeholder='Описание задания (Что нужно сделать)' required></textarea>
      <label><input type='checkbox' name='is_code_assignment' id='is_code_assignment' /> Это задание с кодом</label>
      <textarea name='reference_code' placeholder='Эталонный код (правильное решение)'></textarea>
      <textarea name='expected_output' placeholder='Ожидаемый результат (если отличается от результата эталонного кода)'></textarea>
      <input type='number' name='time_limit' min='1' value='2' placeholder='Лимит времени (секунды)' />
      <input type='number' name='memory_limit' min='8' value='256' placeholder='Лимит памяти (MB)' />
      <input type='hidden' name='tests_json' id='tests_json' value='[]' />
      <div id='tests_builder' style='display:none; border:1px solid #ddd; border-radius:8px; padding:12px; background:#fafafa;'>
        <h4 style='margin:0 0 10px 0;'>Тесты</h4>
        <textarea id='test_input' placeholder='Входные данные теста'></textarea>
        <textarea id='test_expected' placeholder='Ожидаемый вывод'></textarea>
        <button type='button' onclick='addTest()'>Добавить тест</button>
        <div id='tests_count' style='margin-top:8px; color:#2e7d32; font-weight:bold;'></div>
        <div id='tests_error' style='margin-top:8px; color:#c62828; font-weight:bold;'></div>
        <ul id='tests_list' style='margin-top:10px;'></ul>
      </div>
      <select name='language_id' required>
         <option value='71'>Python (3.8.1)</option>
         <option value='62'>Java</option>
         <option value='54'>C++</option>
         <option value='63'>JavaScript</option>
      </select>
      <button type='submit'>Опубликовать задание</button>
    </form>
    <script>
      const codeCheckbox = document.getElementById('is_code_assignment');
      const testsBuilder = document.getElementById('tests_builder');
      const testsList = document.getElementById('tests_list');
      const testsJsonInput = document.getElementById('tests_json');
      const testsCount = document.getElementById('tests_count');
      const testsError = document.getElementById('tests_error');
      const testsData = [];
      const assignmentForm = document.getElementById('assignment_form');

      function renderTests() {{
        testsList.innerHTML = testsData.map((test, index) => `
          <li style='margin:6px 0;'>
            <strong>Тест ${{index + 1}}</strong><br/>
            <small>stdin:</small> <pre>${{(test.input || '').replace(/</g, '&lt;')}}</pre>
            <small>expected:</small> <pre>${{(test.expected_output || '').replace(/</g, '&lt;')}}</pre>
          </li>
        `).join('');
        testsJsonInput.value = JSON.stringify(testsData);
        testsCount.textContent = testsData.length ? `✅ Добавлено тестов: ${{testsData.length}}` : '';
      }}

      function addTest() {{
        const inputEl = document.getElementById('test_input');
        const expectedEl = document.getElementById('test_expected');
        const inputValue = inputEl.value || '';
        const expectedValue = expectedEl.value || '';
        testsData.push({{ input: inputValue, expected_output: expectedValue }});
        inputEl.value = '';
        expectedEl.value = '';
        testsError.textContent = '';
        renderTests();
      }}

      codeCheckbox.addEventListener('change', function() {{
        testsBuilder.style.display = this.checked ? 'block' : 'none';
        if (!this.checked) {{
          testsError.textContent = '';
        }}
      }});

      assignmentForm.addEventListener('submit', function(event) {{
        testsError.textContent = '';
        if (!codeCheckbox.checked) {{
          return;
        }}
        let parsed = [];
        try {{
          parsed = JSON.parse(testsJsonInput.value || '[]');
        }} catch (_) {{
          testsError.textContent = '❌ Невалидный JSON тестов. Добавьте тест заново.';
          event.preventDefault();
          return;
        }}
        if (!Array.isArray(parsed) || parsed.length === 0) {{
          testsError.textContent = '❌ Для задания с кодом нужен минимум 1 тест.';
          event.preventDefault();
        }}
      }});
    </script>
    <h2>Список заданий и ответы студентов</h2>
    <ul>{''.join(assignment_items) or '<li class="card">Заданий пока нет. Создайте первое!</li>'}</ul>
    </body></html>
    """


@app.post("/teacher/access-codes")
def change_access_codes(
    request: Request,
    teacher_code: str = Form(...),
    student_code: str = Form(...),
    db: Session = Depends(get_db)
):
    """Allow a logged-in teacher to change teacher/student access codes."""
    if request.session.get("role") != "teacher":
        return RedirectResponse(url="/")

    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/")

    is_valid, error = validate_access_codes(teacher_code, student_code)
    if not is_valid:
        return RedirectResponse(
            url=f"/teacher?access_code_error={quote_plus(error)}",
            status_code=303,
        )

    update_access_code(db, "teacher", teacher_code, user_id)
    update_access_code(db, "student", student_code, user_id)
    db.commit()

    return RedirectResponse(url="/teacher?access_codes_updated=1", status_code=303)


@app.post("/teacher/assignments")
def add_assignment(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    reference_code: str = Form(""),
    expected_output: str = Form(""),
    language_id: int = Form(...),
    is_code_assignment: Optional[str] = Form(None),
    tests_json: str = Form("[]"),
    time_limit: int = Form(2),
    memory_limit: int = Form(256),
    db: Session = Depends(get_db)
):
    """Add new assignment (teacher only)"""
    if request.session.get("role") != "teacher":
        return RedirectResponse(url="/")
    
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/")
    
    tests, tests_json_valid = parse_tests_json_with_validation(tests_json)
    code_assignment_enabled = is_code_assignment == "on"
    logger.info(
        "Teacher assignment submission: teacher_id=%s title=%s is_code_assignment=%s tests_json_length=%s tests_json_valid=%s parsed_tests_count=%s",
        user_id,
        title,
        code_assignment_enabled,
        len(tests_json or ""),
        tests_json_valid,
        len(tests),
    )

    if code_assignment_enabled and not tests_json_valid:
        error = quote_plus("Невалидный JSON в тестах. Проверьте формат тестов.")
        logger.warning(
            "Teacher assignment rejected due to invalid tests_json: teacher_id=%s title=%s raw_tests_json=%r",
            user_id,
            title,
            tests_json,
        )
        return RedirectResponse(url=f"/teacher?form_error={error}", status_code=303)

    if code_assignment_enabled and not tests:
        error = quote_plus("Для задания с кодом добавьте минимум один тест (вход и ожидаемый вывод).")
        logger.warning(
            "Teacher assignment rejected because code assignment has no tests: teacher_id=%s title=%s",
            user_id,
            title,
        )
        return RedirectResponse(url=f"/teacher?form_error={error}", status_code=303)

    assignment = Assignment(
        teacher_id=user_id,
        title=title,
        description=description,
        reference_code=reference_code,
        expected_output=expected_output,
        language_id=language_id,
        is_code_assignment=code_assignment_enabled,
        tests=tests if code_assignment_enabled else None,
        time_limit=max(1, time_limit),
        memory_limit=max(8, memory_limit),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    stored_tests_count = len(assignment.tests or []) if assignment.is_code_assignment else 0
    logger.info(
        "Assignment saved: assignment_id=%s teacher_id=%s is_code_assignment=%s stored_tests_count=%s stored_tests=%s",
        assignment.id,
        user_id,
        assignment.is_code_assignment,
        stored_tests_count,
        assignment.tests,
    )

    return RedirectResponse(
        url=f"/teacher?assignment_saved=1&tests_saved_count={stored_tests_count}",
        status_code=303,
    )


@app.get("/student", response_class=HTMLResponse)
def student_page(request: Request, db: Session = Depends(get_db)):
    """Student dashboard - view assignments and submit solutions"""
    if request.session.get("role") != "student":
        return RedirectResponse(url="/")
    
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/")
    
    name = html.escape(request.session.get("name", "Ученик"))
    
    # Get all assignments
    assignments = db.query(Assignment).all()
    
    # Get student's own submissions
    student_submissions = db.query(Submission).filter(Submission.student_id == user_id).all()
    submissions_by_assignment = {s.assignment_id: s for s in student_submissions}
    
    cards = []
    for a in assignments:
        language_name = LANGUAGE_ID_TO_NAME.get(a.language_id, "Unknown")
        
        reference_code_display = ""
        
        # Check if student has already submitted for this assignment
        submission = submissions_by_assignment.get(a.id)
        submission_result_display = ""
        if submission:
            status_class, status_text = format_status(submission.status)
            submission_result_display = f"""
            <div style='margin-top: 15px; padding: 15px; border-radius: 8px; border-left: 4px solid;'>
              <h4 style='margin-top: 0;'>📊 Результат проверки:</h4>
              <p style='font-size: 16px; margin: 10px 0;'><span class='{status_class}'>{status_text}</span></p>
            """
            
            if submission.status == SubmissionStatus.ACCEPTED.value:
                submission_result_display += f"""
              <div style='background: #c8e6c9; border-radius: 4px; padding: 10px; margin: 10px 0; color: #2e7d32;'>
                ✅ <strong>Поздравляем! Ваше решение верно!</strong>
              </div>
            """
            elif submission.status == SubmissionStatus.WRONG_ANSWER.value:
                submission_result_display += f"""
              <div style='background: #ffcdd2; border-radius: 4px; padding: 10px; margin: 10px 0;'>
                <strong>❌ Неправильный ответ</strong><br/>
                <strong style='display: block; margin-top: 10px;'>Вывод вашего кода:</strong>
                <pre style='background: #fff3cd; border: 1px solid #ffc107; padding: 10px; margin: 5px 0; max-height: 100px; overflow-y: auto;'>{html.escape(submission.stdout or '(нет вывода)')}</pre>
              </div>
            """
            elif submission.status in [SubmissionStatus.COMPILATION_ERROR.value, SubmissionStatus.RUNTIME_ERROR.value]:
                submission_result_display += f"""
              <div style='background: #ffcdd2; border-radius: 4px; padding: 10px; margin: 10px 0;'>
                <strong>❌ Ошибка:</strong><br/>
                <pre style='background: #fff; border: 1px solid #f44336; padding: 10px; margin: 5px 0; color: #c62828; max-height: 100px; overflow-y: auto;'>{html.escape(submission.stderr or submission.stdout or '(нет информации об ошибке)')}</pre>
              </div>
            """
            
            submission_result_display += f"""
              <small style='color: #666; display: block; margin-top: 10px;'>Отправлено: {submission.created_at.strftime('%Y-%m-%d %H:%M:%S')}</small>
            </div>
            """
        
        submission_form_html = f"""
          <form method='post' action='/student/submissions'>
            <input type='hidden' name='assignment_id' value='{a.id}' />
            <textarea name='code' placeholder='Напишите ваш код здесь...' required style='font-family: monospace; min-height: 150px;'></textarea>
            <button type='submit'>Отправить решение на проверку</button>
          </form>
        """

        if a.is_code_assignment:
            submission_form_html = f"""
              <form onsubmit='submitCode(event, {a.id}, this)'>
                <input type='hidden' name='assignment_id' value='{a.id}' />
                <label>Язык:
                  <select name='language' required>
                    <option value='python'>Python</option>
                    <option value='cpp'>C++</option>
                    <option value='java'>Java</option>
                    <option value='javascript'>JavaScript</option>
                  </select>
                </label>
                <textarea name='code' placeholder='Напишите ваш код здесь...' required style='font-family: monospace; min-height: 200px;'></textarea>
                <button type='submit'>Запустить автопроверку</button>
                <div class='code-submit-result' style='margin-top:10px;'></div>
              </form>
            """

        cards.append(f"""
        <li class='card'>
          <h3>{html.escape(a.title)}</h3>
          <p>{html.escape(a.description)}</p>
          <p><strong>Тип:</strong> {'Кодинг' if a.is_code_assignment else 'Текстовое'}</p>
          <p><strong>Язык программирования:</strong> <span style='background: #e3f2fd; padding: 2px 8px; border-radius: 4px; font-weight: bold;'>{language_name}</span></p>
          {reference_code_display}
          {submission_result_display}
          {submission_form_html}
        </li>
        """)
    
    return f"""
    <html><body>{UI_STYLES}
    <h1>Панель ученика: {name} <span class='monitoring-indicator monitoring-active'>📡 Мониторинг активен</span></h1>
    <a href='/' class='logout-btn'>Выйти из системы</a>
    <h2>Доступные задания для выполнения</h2>
    <ul>{''.join(cards) or '<li class="card">Отлично! Преподаватель еще не добавил заданий. Отдыхайте.</li>'}</ul>
    
    <script>
    // Student Activity Monitoring for Academic Integrity
    let currentSubmissionId = null;
    
    // Initialize monitoring when page loads
    function initializeMonitoring() {{
        console.log('Student activity monitoring initialized');
        console.info('⚠️ Academic integrity monitoring is active on this session');
    }}
    
    // Track tab visibility changes
    document.addEventListener('visibilitychange', function() {{
        const eventType = document.hidden ? 'tab_hidden' : 'tab_visible';
        const description = document.hidden 
            ? 'Student switched tabs or minimized window' 
            : 'Student returned to the tab';
        logActivity(eventType, description);
    }});
    
    // Track window focus changes
    window.addEventListener('blur', function() {{
        logActivity('focus_lost', 'Window lost focus');
    }});
    
    window.addEventListener('focus', function() {{
        logActivity('focus_gained', 'Window regained focus');
    }});
    
    // Track keyboard and mouse activity
    let activityTimeout;
    function resetActivityTimeout() {{
        clearTimeout(activityTimeout);
        activityTimeout = setTimeout(function() {{
            // Optional: log inactivity after X seconds
        }}, 60000); // 60 seconds
    }}
    
    document.addEventListener('keydown', function() {{
        resetActivityTimeout();
    }});
    
    document.addEventListener('mousemove', function() {{
        resetActivityTimeout();
    }});
    
    // Send activity log to server
    function logActivity(activityType, description) {{
        console.log('Activity:', activityType, '-', description);
        const isSuspicious = (activityType === 'focus_lost' || activityType === 'tab_hidden');
        if (!isSuspicious) return;
        if (!currentSubmissionId) return;
        const formData = new FormData();
        formData.append('activity_type', activityType);
        formData.append('description', description);
        formData.append('submission_id', currentSubmissionId);

        fetch('/api/activity', {{
            method: 'POST',
            body: formData
        }})
        .then(r => r.json())
        .then(data => {{
            if (data.status === 'ok') {{
                console.log('✓ Activity logged on server');
            }}
        }})
        .catch(e => console.error('Error logging activity:', e));
    }}

    async function submitCode(event, assignmentId, formElement) {{
        event.preventDefault();
        const resultBox = formElement.querySelector('.code-submit-result');
        resultBox.innerHTML = "<div style='padding:10px; border-radius:8px; background:#f5f5f5; color:#666;'>📤 Отправка кода на сервер...</div>";
        try {{
            const formData = new FormData(formElement);
            const payload = {{
                assignment_id: assignmentId,
                language: formData.get('language'),
                code: formData.get('code')
            }};
            const response = await fetch('/submit_code', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload)
            }});
            if (!response.ok) {{
                let detail = `HTTP ${{response.status}}`;
                try {{
                    const errData = await response.json();
                    detail = errData.detail || detail;
                }} catch (_) {{}}
                throw new Error(detail);
            }}
            const data = await response.json();
            if (data.verdict === 'No tests') {{
                resultBox.innerHTML = `
                    <div style="padding:10px; border-radius:8px; background:#ffcdd2; color:#c62828;">
                        <strong>❌ Автопроверка недоступна:</strong> тесты не настроены для этого задания.<br/>
                        <small>${{(data.details || 'Попросите учителя добавить минимум один тест и переопубликовать задание.').replace(/</g, '&lt;')}}</small>
                    </div>
                `;
                return;
            }}
            if (data.submission_id) {{
                currentSubmissionId = data.submission_id;
                 
                // Start streaming the live output
                streamSubmissionOutput(data.submission_id, resultBox);
            }} else {{
                const escapedDetails = (data.details || '').replace(/</g, '&lt;');
                resultBox.innerHTML = `
                    <div style="padding:10px; border-radius:8px; background:#f5f5f5;">
                        <strong>Вердикт:</strong> ${{data.verdict}}<br/>
                        <strong>Пройдено:</strong> ${{data.tests_passed}} / ${{data.total_tests}}<br/>
                        <small>${{escapedDetails}}</small>
                    </div>
                `;
            }}
        }} catch (error) {{
            resultBox.innerHTML = "<span style='color:#c62828;'>❌ Ошибка отправки решения: " + (error.message || 'неизвестная ошибка') + "</span>";
        }}
    }}
     
    function streamSubmissionOutput(submissionId, resultBox) {{
        resultBox.innerHTML = "<div style='padding:10px; border-radius:8px; background:#f5f5f5; color:#666;'>⏳ Компиляция кода...</div>";
         
        const eventSource = new EventSource(`/api/submission-stream/${{submissionId}}`);
        let outputLines = [];
         
        eventSource.onmessage = function(event) {{
            try {{
                const update = JSON.parse(event.data);
                 
                if (update.type === 'error') {{
                    resultBox.innerHTML = `<div style='padding:10px; border-radius:8px; background:#ffcdd2; color:#c62828;'>❌ Ошибка: ${{(update.error || 'неизвестная ошибка').replace(/</g, '&lt;')}}</div>`;
                    eventSource.close();
                    return;
                }}
                 
                if (update.type === 'status') {{
                    let displayHtml = `<div style="padding:10px; border-radius:8px; background:#f5f5f5; font-family: monospace; font-size: 12px;">`;
                     
                    // Show compilation output
                    if (update.compile_output) {{
                        displayHtml += `<div style="margin-bottom:10px;"><strong style='color:#f57c00;'>🔧 Вывод компилятора:</strong><br/>`;
                        displayHtml += `<pre style="background:#fff; border:1px solid #f57c00; padding:8px; margin:5px 0; overflow-x: auto; max-height: 150px;">${{(update.compile_output || '').replace(/</g, '&lt;')}}</pre></div>`;
                    }}
                     
                    // Show execution output
                    if (update.stdout) {{
                        displayHtml += `<div style="margin-bottom:10px;"><strong style='color:#2196F3;'>▶ Вывод программы:</strong><br/>`;
                        displayHtml += `<pre style="background:#f5f5f5; border:1px solid #2196F3; padding:8px; margin:5px 0; overflow-x: auto; max-height: 150px;">${{(update.stdout || '').replace(/</g, '&lt;')}}</pre></div>`;
                    }}
                     
                    // Show errors
                    if (update.stderr) {{
                        displayHtml += `<div style="margin-bottom:10px;"><strong style='color:#f44336;'>⚠ Ошибка выполнения:</strong><br/>`;
                        displayHtml += `<pre style="background:#ffebee; border:1px solid #f44336; padding:8px; margin:5px 0; overflow-x: auto; max-height: 150px; color:#c62828;">${{(update.stderr || '').replace(/</g, '&lt;')}}</pre></div>`;
                    }}
                     
                    // Show status
                    let statusText = '🔄 Выполняется...';
                    let statusColor = '#FFA500';
                    if (update.status_id === 3) {{ statusText = '✅ Принято'; statusColor = '#4CAF50'; }}
                    else if (update.status_id === 4) {{ statusText = '❌ Неправильный ответ'; statusColor = '#f44336'; }}
                    else if (update.status_id === 5) {{ statusText = '⏱ Превышено время выполнения'; statusColor = '#FF6F00'; }}
                    else if (update.status_id === 6) {{ statusText = '🔴 Ошибка компиляции'; statusColor = '#f44336'; }}
                    else if (update.status_id >= 7 && update.status_id <= 12) {{ statusText = '⚠ Ошибка выполнения'; statusColor = '#FF6F00'; }}
                     
                    displayHtml += `<div style="padding:10px; background:${{statusColor}}15; border-left:4px solid ${{statusColor}};"><strong style="color:${{statusColor}};">Статус: ${{statusText}}</strong>`;
                    if (update.time) {{ displayHtml += `<br/>⏱ Время: ${{update.time}} сек`; }}
                    if (update.memory) {{ displayHtml += `<br/>💾 Память: ${{update.memory}} МБ`; }}
                    displayHtml += `</div>`;
                     
                    displayHtml += `</div>`;
                    resultBox.innerHTML = displayHtml;
                     
                    if (update.complete) {{
                        eventSource.close();
                    }}
                }}
            }} catch (e) {{
                console.error('Error parsing stream data:', e);
            }}
        }};
         
        eventSource.onerror = function(event) {{
            console.error('Stream error:', event);
            resultBox.innerHTML = "<span style='color:#c62828;'>❌ Ошибка соединения с сервером</span>";
            eventSource.close();
        }};
    }}
     
    // Initialize on load
    window.addEventListener('load', initializeMonitoring);
    </script>
    </body></html>
    """


def resolve_language_id(language: Optional[str], default_language_id: int) -> int:
    """Resolve language text (python/cpp/java/javascript) to Judge0 language_id."""
    if not language:
        return default_language_id
    normalized = language.strip().lower()
    if normalized in LANGUAGE_NAME_TO_ID:
        return LANGUAGE_NAME_TO_ID[normalized]
    if normalized.isdigit():
        return int(normalized)
    return default_language_id


def evaluate_and_store_submission(
    db: Session,
    assignment: Assignment,
    student_id: int,
    code: str,
    language_id: int,
) -> tuple[Submission, dict]:
    """Evaluate and persist a submission, returning DB row and API payload."""
    submission = Submission(
        assignment_id=assignment.id,
        student_id=student_id,
        code=code,
        language_id=language_id,
        status=SubmissionStatus.PENDING.value,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    if assignment.is_code_assignment:
        tests = assignment.tests or []
        logger.info(
            "Evaluating code submission with tests: submission_id=%s assignment_id=%s student_id=%s tests_count=%s",
            submission.id,
            assignment.id,
            student_id,
            len(tests),
        )
        evaluation = evaluate_code_with_tests(
            source_code=code,
            language_id=language_id,
            tests=tests,
            time_limit=assignment.time_limit or 2,
            memory_limit=assignment.memory_limit or 256,
        )

        verdict = evaluation.get("verdict", SubmissionStatus.ERROR.value)
        failed_test_number = evaluation.get("failed_test_number")
        test_results = evaluation.get("test_results") or []
        last_result = test_results[-1] if test_results else {}
        status = SubmissionStatus.ACCEPTED.value if verdict == "Accepted" else verdict
        logger.info(
            "Evaluation completed: submission_id=%s assignment_id=%s verdict=%s tests_passed=%s total_tests=%s failed_test_number=%s",
            submission.id,
            assignment.id,
            verdict,
            evaluation.get("tests_passed", 0),
            evaluation.get("total_tests", len(tests)),
            failed_test_number,
        )

        submission.status = status
        submission.verdict = verdict
        submission.failed_test_number = failed_test_number
        submission.failed_test = failed_test_number
        submission.tests_passed = evaluation.get("tests_passed", 0)
        submission.total_tests = evaluation.get("total_tests", len(tests))
        submission.test_results = test_results
        submission.stdout = last_result.get("actual_output", "")
        submission.stderr = last_result.get("stderr", "")
        submission.time_used = float(last_result.get("time") or 0)
        submission.judge0_token = evaluation.get("token")  # Store the first test's token for streaming
        submission.evaluated_at = datetime.utcnow()
        db.commit()

        details = evaluation.get("details") or verdict
        if failed_test_number:
            details = f"{verdict}. Failed test: {failed_test_number}"
        return submission, {
            "verdict": verdict,
            "details": details,
            "tests_passed": evaluation.get("tests_passed", 0),
            "total_tests": evaluation.get("total_tests", len(tests)),
        }

    # Legacy single-output path (non-code assignments)
    parsed_stdin, parsed_expected_output = extract_legacy_io_from_description(assignment.description or "")
    fallback_expected_output = assignment.expected_output or parsed_expected_output
    legacy_stdin = parsed_stdin

    reference_output = ""
    has_expected_output = False
    if assignment.reference_code:
        reference_result = evaluate_submission(
            assignment.reference_code,
            assignment.language_id,
            "",
            legacy_stdin,
        )
        reference_output = reference_result.get("stdout", "")
        if reference_result["status"] != SubmissionStatus.ACCEPTED.value and fallback_expected_output:
            reference_output = fallback_expected_output
        has_expected_output = bool(reference_output.strip())
    elif fallback_expected_output:
        reference_output = fallback_expected_output
        has_expected_output = True

    result = evaluate_submission(
        code,
        assignment.language_id,
        reference_output if reference_output else fallback_expected_output,
        legacy_stdin,
    )
    if not has_expected_output and result["status"] == SubmissionStatus.ACCEPTED.value:
        result["status"] = SubmissionStatus.PENDING.value

    submission.status = result["status"]
    submission.verdict = result["status"]
    submission.stdout = result.get("stdout", "")
    submission.stderr = result.get("stderr", "")
    submission.judge0_token = result.get("token")
    submission.evaluated_at = datetime.utcnow()
    db.commit()

    return submission, {
        "verdict": result["status"],
        "details": result["status"],
        "tests_passed": 0,
        "total_tests": 0,
    }


@app.post("/submit_code")
async def submit_code(
    request: Request,
    db: Session = Depends(get_db),
):
    """JSON API for code autograding by tests."""
    if request.session.get("role") != "student":
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    assignment_id = int(payload.get("assignment_id", 0))
    code = str(payload.get("code", "")).strip()
    language = str(payload.get("language", "")).strip()
    student_id = request.session.get("user_id")

    if not student_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not assignment_id or not code:
        raise HTTPException(status_code=400, detail="assignment_id and code are required")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    language_id = resolve_language_id(language, assignment.language_id)
    logger.info(
        "submit_code request: student_id=%s assignment_id=%s assignment_is_code=%s assignment_tests_count=%s language_id=%s",
        student_id,
        assignment_id,
        assignment.is_code_assignment,
        len(assignment.tests or []) if assignment.is_code_assignment else 0,
        language_id,
    )

    try:
        submission, response_payload = evaluate_and_store_submission(
            db=db,
            assignment=assignment,
            student_id=student_id,
            code=code,
            language_id=language_id,
        )
        response_payload["submission_id"] = submission.id
        # Include judge0_token if available (for SSE streaming)
        judge0_token = getattr(submission, 'judge0_token', None)
        if judge0_token:
            response_payload["judge0_token"] = judge0_token
        return JSONResponse(response_payload)
    except Exception as exc:
        logger.error(f"submit_code failed: {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Code evaluation failed")


@app.get("/api/submission-stream/{submission_id}")
async def submission_stream(
    submission_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Stream real-time compilation and execution output for a submission.
    Uses Server-Sent Events (SSE) to send updates to the client.
    """
    if request.session.get("role") != "student":
        raise HTTPException(status_code=401, detail="Unauthorized")

    student_id = request.session.get("user_id")
    if not student_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Get the submission
    submission = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.student_id == student_id
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # If there's no judge0_token, send the current stored result and close
    if not submission.judge0_token:
        async def event_generator():
            yield f"data: {json.dumps({'type': 'status', 'status_id': -1, 'status': submission.status, 'compile_output': '', 'stdout': submission.stdout or '', 'stderr': submission.stderr or '', 'complete': True})}\n\n"
        
        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Stream the live results from Judge0
    async def event_generator():
        logger.info(f"Starting stream for submission {submission_id}, token {submission.judge0_token}")
        
        try:
            for update in stream_judge0_result(
                token=submission.judge0_token,
                max_wait=30,
                poll_interval=0.5
            ):
                # Format as Server-Sent Event
                event_data = {
                    'type': 'status',
                    'status_id': update.get('status_id'),
                    'compile_output': update.get('compile_output', ''),
                    'stdout': update.get('stdout', ''),
                    'stderr': update.get('stderr', ''),
                    'time': update.get('time', '0'),
                    'memory': update.get('memory', '0'),
                    'complete': update.get('complete', False),
                }
                
                logger.debug(f"Streaming update: {event_data}")
                yield f"data: {json.dumps(event_data)}\n\n"
                
                if update.get('complete'):
                    # Update the submission in the database with final result
                    submission.status = update.get('status_id', -1)
                    db.commit()
                    break
        except Exception as e:
            logger.error(f"Error in submission stream: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Stream processing error', 'complete': True})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/student/submissions")
def submit_solution(
    request: Request,
    assignment_id: int = Form(...),
    code: str = Form(...),
    language: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Submit code solution for evaluation (student only)."""
    if request.session.get("role") != "student":
        return RedirectResponse(url="/")

    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/")

    if not code or not code.strip():
        logger.warning(f"Empty submission from user {user_id}")
        return RedirectResponse(url="/student", status_code=303)

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        logger.warning(f"Invalid assignment {assignment_id} from user {user_id}")
        return RedirectResponse(url="/student", status_code=303)

    language_id = resolve_language_id(language, assignment.language_id)

    try:
        evaluate_and_store_submission(
            db=db,
            assignment=assignment,
            student_id=user_id,
            code=code,
            language_id=language_id,
        )
    except Exception as exc:
        logger.error(f"Error during submission: {str(exc)}", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass

    return RedirectResponse(url="/student", status_code=303)


@app.post("/api/activity")
def log_activity(
    request: Request,
    activity_type: str = Form(...),
    description: str = Form(""),
    submission_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """API endpoint for logging student activity (for academic integrity monitoring)"""
    user_id = request.session.get("user_id")
    if not user_id or request.session.get("role") != "student":
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not submission_id:
        return {"status": "ignored"}
    
    # Log the activity
    activity = StudentActivity(
        student_id=user_id,
        submission_id=submission_id,
        activity_type=activity_type,
        description=description,
        is_suspicious=(activity_type in ["focus_lost", "tab_hidden"])
    )
    db.add(activity)
    db.commit()
    
    return {"status": "ok", "activity_id": activity.id}


@app.on_event("startup")
async def startup():
    """Initialize database on startup"""
    try:
        init_db()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"✗ Database initialization error: {e}")
