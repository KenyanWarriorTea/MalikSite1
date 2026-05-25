"""
MalikSite1 - Judge0 Educational Platform
Web application for teachers to publish assignments and students to submit solutions.
"""
import html
import os
import secrets
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Form, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from database import init_db, get_db
from models import User, Assignment, Submission, StudentActivity, SubmissionStatus
from judge0_client import evaluate_submission

# Initialize database
init_db()

app = FastAPI(title="MalikSite1")

SESSION_SECRET = secrets.token_urlsafe(32)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Secret codes for access
TEACHER_CODE = "teacher123"
STUDENT_CODE = "student123"

# UI Styles
UI_STYLES = """
<style>
body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.6; background: #f9f9f9; color: #333; }
form { display: flex; flex-direction: column; gap: 12px; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
input, textarea, select { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; box-sizing: border-box; }
textarea { min-height: 100px; }
button { padding: 12px 24px; border: none; border-radius: 8px; color: white; background: #212121; font-weight: bold; font-size: 16px; cursor: pointer; transition: 0.2s; width: fit-content; }
button:hover { background: #444; }
.logout-btn { display: inline-block; padding: 8px 16px; background: #e0e0e0; color: #333; border-radius: 6px; text-decoration: none; font-size: 14px; margin-bottom: 20px; font-weight: bold; }
.logout-btn:hover { background: #ccc; }
.card { background: white; padding: 20px; border-radius: 12px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); list-style: none; }
pre { background: #f1f1f1; padding: 10px; border-radius: 6px; font-family: monospace; overflow-x: auto; }
.status-accepted { color: green; font-weight: bold; }
.status-pending { color: orange; font-weight: bold; }
.status-error { color: red; font-weight: bold; }
.status-wrong { color: #ff6b6b; font-weight: bold; }
.activity-log { background: #f0f0f0; padding: 10px; border-radius: 6px; margin-top: 10px; font-size: 12px; }
.activity-suspicious { background: #ffe0e0; color: #c00; }
</style>
"""

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


# ============================================================================
# Routes
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def login_page():
    """Login page for teachers and students"""
    return f"""
    <html><body>{UI_STYLES}
    <div style='max-width: 400px; margin: 100px auto; text-align: center;'>
        <h1>Вход в систему</h1>
        <form method='post' action='/login'>
          <input name='name' placeholder='Ваше имя' required />
          <input type='password' name='access_code' placeholder='Секретный код доступа' required />
          <button type='submit' style='width: 100%;'>Войти</button>
        </form>
        <p style='color: #666; font-size: 12px; margin-top: 20px;'>Учитель: teacher123 | Ученик: student123</p>
    </div>
    </body></html>
    """


@app.post("/login")
def login(request: Request, name: str = Form(...), access_code: str = Form(...), db: Session = Depends(get_db)):
    """Handle login for teachers and students"""
    if access_code == TEACHER_CODE:
        role = "teacher"
    elif access_code == STUDENT_CODE:
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
    
    assignment_items = []
    for a in assignments:
        submissions = db.query(Submission).filter(Submission.assignment_id == a.id).all()
        
        rows = []
        for s in submissions:
            student = db.query(User).filter(User.id == s.student_id).first()
            student_name = html.escape(student.name if student else "Unknown")
            status_class, status_text = format_status(s.status)
            
            rows.append(
                f"<li style='margin-top:10px;'><b>{student_name}</b>: "
                f"<span class='{status_class}'>{status_text}</span>"
                f"<pre>{html.escape(s.code)}</pre>"
                f"<small style='color: #666;'>Отправлено: {s.created_at.strftime('%Y-%m-%d %H:%M:%S')}</small>"
                f"</li>"
            )
        
        assignment_items.append(
            f"<li class='card'><h3>Задание: {html.escape(a.title)}</h3>"
            f"<p>{html.escape(a.description)}</p>"
            f"<ul>{''.join(rows) or '<li>Решений пока нет</li>'}</ul>"
            f"</li>"
        )
    
    return f"""
    <html><body>{UI_STYLES}
    <h1>Панель учителя: {name}</h1>
    <a href='/' class='logout-btn'>Выйти из системы</a>
    <form method='post' action='/teacher/assignments'>
      <h2>Добавить задание</h2>
      <input name='title' placeholder='Название задания' required />
      <textarea name='description' placeholder='Описание задания (Что нужно сделать)' required></textarea>
      <input name='expected_output' placeholder='Ожидаемый результат (например: 42)' />
      <select name='language_id'>
         <option value='71'>Python (3.8.1)</option>
         <option value='62'>Java</option>
         <option value='54'>C++</option>
      </select>
      <button type='submit'>Опубликовать задание</button>
    </form>
    <h2>Список заданий и ответы студентов</h2>
    <ul>{''.join(assignment_items) or '<li class="card">Заданий пока нет. Создайте первое!</li>'}</ul>
    </body></html>
    """


@app.post("/teacher/assignments")
def add_assignment(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    expected_output: str = Form(""),
    language_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Add new assignment (teacher only)"""
    if request.session.get("role") != "teacher":
        return RedirectResponse(url="/")
    
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/")
    
    assignment = Assignment(
        teacher_id=user_id,
        title=title,
        description=description,
        expected_output=expected_output,
        language_id=language_id
    )
    db.add(assignment)
    db.commit()
    
    return RedirectResponse(url="/teacher", status_code=303)


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
    
    cards = []
    for a in assignments:
        cards.append(f"""
        <li class='card'>
          <h3>{html.escape(a.title)}</h3>
          <p>{html.escape(a.description)}</p>
          <form method='post' action='/student/submissions'>
            <input type='hidden' name='assignment_id' value='{a.id}' />
            <textarea name='code' placeholder='Напишите ваш код здесь...' required></textarea>
            <button type='submit'>Отправить решение на проверку</button>
          </form>
        </li>
        """)
    
    return f"""
    <html><body>{UI_STYLES}
    <h1>Панель ученика: {name}</h1>
    <a href='/' class='logout-btn'>Выйти из системы</a>
    <h2>Доступные задания для выполнения</h2>
    <ul>{''.join(cards) or '<li class="card">Отлично! Преподаватель еще не добавил заданий. Отдыхайте.</li>'}</ul>
    
    <script>
    // Activity monitoring for academic integrity
    let activityData = {{
        focus_lost_count: 0,
        tab_hidden_count: 0
    }};
    
    // Track tab visibility changes
    document.addEventListener('visibilitychange', function() {{
        if (document.hidden) {{
            logActivity('tab_hidden', 'Student switched tabs or minimized window');
            activityData.tab_hidden_count++;
        }} else {{
            logActivity('tab_visible', 'Student returned to the tab');
        }}
    }});
    
    // Track window focus changes
    window.addEventListener('blur', function() {{
        logActivity('focus_lost', 'Window lost focus');
        activityData.focus_lost_count++;
    }});
    
    window.addEventListener('focus', function() {{
        logActivity('focus_gained', 'Window regained focus');
    }});
    
    // Send activity log to server
    function logActivity(activityType, description) {{
        console.log('Activity:', activityType, description);
        // Will be implemented with submission tracking
    }}
    </script>
    </body></html>
    """


@app.post("/student/submissions")
def submit_solution(
    request: Request,
    assignment_id: int = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    """Submit code solution for evaluation (student only)"""
    if request.session.get("role") != "student":
        return RedirectResponse(url="/")
    
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/")
    
    # Get assignment
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        return RedirectResponse(url="/student")
    
    # Create submission with pending status
    submission = Submission(
        assignment_id=assignment_id,
        student_id=user_id,
        code=code,
        status=SubmissionStatus.PENDING.value
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    
    # Evaluate code using Judge0
    result = evaluate_submission(
        code,
        assignment.language_id,
        assignment.expected_output,
        ""
    )
    
    # Update submission with results
    submission.status = result["status"]
    submission.stdout = result.get("stdout", "")
    submission.stderr = result.get("stderr", "")
    submission.judge0_token = result.get("token")
    submission.evaluated_at = datetime.utcnow()
    
    db.commit()
    
    return RedirectResponse(url="/student", status_code=303)


@app.post("/api/activity")
def log_activity(
    request: Request,
    activity_type: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    """API endpoint for logging student activity (for academic integrity monitoring)"""
    user_id = request.session.get("user_id")
    if not user_id or request.session.get("role") != "student":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # In a real implementation, we'd link this to the current submission
    # For now, just log the activity
    activity = StudentActivity(
        student_id=user_id,
        submission_id=None,  # Will be updated when submission is active
        activity_type=activity_type,
        description=description,
        is_suspicious=(activity_type in ["focus_lost", "tab_hidden"])
    )
    db.add(activity)
    db.commit()
    
    return {"status": "ok"}


@app.on_event("startup")
async def startup():
    """Initialize database on startup"""
    try:
        init_db()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"✗ Database initialization error: {e}")
