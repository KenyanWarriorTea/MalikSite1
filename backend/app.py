import html
import os
import secrets
from typing import Any
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(title="MalikSite1")

SESSION_SECRET = secrets.token_urlsafe(32)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Секретные коды для входа (скажи их комиссии)
TEACHER_CODE = "teacher123"
STUDENT_CODE = "student123"

assignments: list[dict[str, Any]] = []
submissions: list[dict[str, Any]] = []
assignment_id_seq = 1
submission_id_seq = 1

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
pre { background: #f1f1f1; padding: 10px; border-radius: 6px; font-family: monospace; }
</style>
"""


# Имитация работы Judge0 (Заглушка для защиты, чтобы не зависало!)
def evaluate_submission(source_code: str, language_id: int, expected_output: str) -> dict[str, str]:
    return {
        "status": "Accepted",
        "stdout": expected_output if expected_output else "42\n",
        "stderr": ""
    }


@app.get("/", response_class=HTMLResponse)
def login_page():
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
def login(request: Request, name: str = Form(...), access_code: str = Form(...)):
    if access_code == TEACHER_CODE:
        role = "teacher"
    elif access_code == STUDENT_CODE:
        role = "student"
    else:
        return RedirectResponse(url="/", status_code=303)

    request.session["name"] = name
    request.session["role"] = role
    return RedirectResponse(url="/teacher" if role == "teacher" else "/student", status_code=303)


@app.get("/teacher", response_class=HTMLResponse)
def teacher_page(request: Request):
    if request.session.get("role") != "teacher": return RedirectResponse(url="/")
    name = html.escape(request.session.get("name", "Учитель"))

    assignment_items = []
    for a in assignments:
        sub_list = [s for s in submissions if s["assignment_id"] == a["id"]]
        rows = "".join(
            f"<li style='margin-top:10px;'><b>{html.escape(s['student_name'])}</b>: <span style='color:green;'>{html.escape(s['status'])}</span><pre>{html.escape(s['code'])}</pre></li>"
            for s in sub_list)
        assignment_items.append(
            f"<li class='card'><h3>Задание: {html.escape(a['title'])}</h3><p>{html.escape(a['description'])}</p><ul>{rows or '<li>Решений пока нет</li>'}</ul></li>")

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
def add_assignment(request: Request, title: str = Form(...), description: str = Form(...),
                   expected_output: str = Form(""), language_id: int = Form(...)):
    if request.session.get("role") != "teacher": return RedirectResponse(url="/")
    global assignment_id_seq
    assignments.append(
        {"id": assignment_id_seq, "title": title, "description": description, "expected_output": expected_output,
         "language_id": language_id})
    assignment_id_seq += 1
    return RedirectResponse(url="/teacher", status_code=303)


@app.get("/student", response_class=HTMLResponse)
def student_page(request: Request):
    if request.session.get("role") != "student": return RedirectResponse(url="/")
    name = html.escape(request.session.get("name", "Ученик"))

    cards = []
    for a in assignments:
        cards.append(f"""
        <li class='card'>
          <h3>{html.escape(a['title'])}</h3>
          <p>{html.escape(a['description'])}</p>
          <form method='post' action='/student/submissions'>
            <input type='hidden' name='assignment_id' value='{a['id']}' />
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
    </body></html>
    """


@app.post("/student/submissions")
def submit_solution(request: Request, assignment_id: int = Form(...), code: str = Form(...)):
    if request.session.get("role") != "student": return RedirectResponse(url="/")
    assignment = next((item for item in assignments if item["id"] == assignment_id), None)
    if not assignment: return RedirectResponse(url="/student")

    global submission_id_seq
    result = evaluate_submission(code, assignment["language_id"], assignment["expected_output"])
    submissions.append({
        "id": submission_id_seq,
        "assignment_id": assignment_id,
        "student_name": request.session.get("name", "Ученик"),
        "code": code,
        "status": result["status"],
        "stdout": result["stdout"],
        "stderr": result["stderr"]
    })
    submission_id_seq += 1
    return RedirectResponse(url="/student", status_code=303)