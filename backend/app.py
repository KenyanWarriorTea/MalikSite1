"""
MalikSite1 - Judge0 Educational Platform
Web application for teachers to publish assignments and students to submit solutions.
Includes student activity monitoring for academic integrity.
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
from judge0_client import evaluate_submission, compare_outputs
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

# Secret codes for access
TEACHER_CODE = "teacher123"
STUDENT_CODE = "student123"

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
        <p style='color: #666; font-size: 12px; margin-top: 20px;'>
          <strong>Тестовые коды:</strong><br/>
          Учитель: teacher123<br/>
          Ученик: student123
        </p>
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
        
        # Get language name
        language_names = {71: "Python", 62: "Java", 54: "C++", 63: "JavaScript"}
        language_name = language_names.get(a.language_id, "Unknown")
        
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
            f"<p><strong>Язык:</strong> {language_name}</p>"
            f"{reference_display}"
            f"<h4 style='margin-top: 20px;'>Ответы студентов ({len(submissions)}):</h4>"
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
      <textarea name='reference_code' placeholder='Эталонный код (правильное решение)' required></textarea>
      <select name='language_id' required>
         <option value='71'>Python (3.8.1)</option>
         <option value='62'>Java</option>
         <option value='54'>C++</option>
         <option value='63'>JavaScript</option>
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
    reference_code: str = Form(""),
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
        reference_code=reference_code,
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
        # Get language name from ID
        language_names = {71: "Python", 62: "Java", 54: "C++", 63: "JavaScript"}
        language_name = language_names.get(a.language_id, "Unknown")
        
        reference_code_display = ""
        if a.reference_code:
            reference_code_display = f"""
            <div style='margin-top: 15px; padding: 15px; background: #f0f8ff; border-radius: 8px; border-left: 4px solid #2196F3;'>
              <h4 style='margin-top: 0;'>📝 Эталонный код:</h4>
              <pre style='background: #fff; border: 1px solid #ddd;'>{html.escape(a.reference_code)}</pre>
            </div>
            """
        
        cards.append(f"""
        <li class='card'>
          <h3>{html.escape(a.title)}</h3>
          <p>{html.escape(a.description)}</p>
          <p><strong>Язык:</strong> {language_name}</p>
          {reference_code_display}
          <form method='post' action='/student/submissions'>
            <input type='hidden' name='assignment_id' value='{a.id}' />
            <textarea name='code' placeholder='Напишите ваш код здесь...' required style='font-family: monospace; min-height: 150px;'></textarea>
            <button type='submit'>Отправить решение на проверку</button>
          </form>
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
        
        // Warn student about monitoring
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
        
        // Only send suspicious activities immediately to server
        const isSuspicious = (activityType === 'focus_lost' || activityType === 'tab_hidden');
        if (isSuspicious) {{
            const formData = new FormData();
            formData.append('activity_type', activityType);
            formData.append('description', description);
            if (currentSubmissionId) {{
                formData.append('submission_id', currentSubmissionId);
            }}
            
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
    }}
    
    // Initialize on load
    window.addEventListener('load', initializeMonitoring);
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
    
    try:
        # Validate code is not empty
        if not code or not code.strip():
            logger.warning(f"Empty submission from user {user_id}")
            return RedirectResponse(url="/student", status_code=303)
        
        # Get assignment
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment:
            logger.warning(f"Invalid assignment {assignment_id} from user {user_id}")
            return RedirectResponse(url="/student", status_code=303)
        
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
        
        logger.info(f"Submission {submission.id} created for user {user_id}, assignment {assignment_id}")
        
        # Evaluate code using Judge0
        try:
            # First, execute the reference code to get the expected output
            reference_output = ""
            if assignment.reference_code:
                logger.info(f"Evaluating reference code for assignment {assignment_id}")
                reference_result = evaluate_submission(
                    assignment.reference_code,
                    assignment.language_id,
                    "",
                    ""
                )
                reference_output = reference_result.get("stdout", "")
                
                # If reference code has errors, log it
                if reference_result["status"] != SubmissionStatus.ACCEPTED.value:
                    logger.warning(f"Reference code evaluation failed: {reference_result['status']}")
            
            # Now evaluate the student's code
            result = evaluate_submission(
                code,
                assignment.language_id,
                reference_output if reference_output else (assignment.expected_output or ""),
                ""
            )
            
            # Check if output matches the reference output
            if reference_output and result.get("stdout"):
                if compare_outputs(result.get("stdout", ""), reference_output):
                    result["status"] = SubmissionStatus.ACCEPTED.value
                else:
                    result["status"] = SubmissionStatus.WRONG_ANSWER.value
            
            # Update submission with results
            submission.status = result["status"]
            submission.stdout = result.get("stdout", "")
            submission.stderr = result.get("stderr", "")
            submission.judge0_token = result.get("token")
            submission.evaluated_at = datetime.utcnow()
            
            logger.info(f"Submission {submission.id} evaluated: {result['status']}")
        except Exception as e:
            logger.error(f"Judge0 evaluation error: {str(e)}", exc_info=True)
            submission.status = SubmissionStatus.ERROR.value
            submission.stderr = f"Evaluation service error: {str(e)}"
            submission.evaluated_at = datetime.utcnow()
        
        db.commit()
        
    except Exception as e:
        logger.error(f"Error during submission: {str(e)}", exc_info=True)
        # Try to rollback if something went wrong
        try:
            db.rollback()
        except:
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
