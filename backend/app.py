import html
import os
import secrets
from typing import Any

import requests
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(title="MalikSite1")

JUDGE0_URL = os.getenv("JUDGE0_URL", "http://judge0:2358")
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

assignments: list[dict[str, Any]] = []
submissions: list[dict[str, Any]] = []
assignment_id_seq = 1
submission_id_seq = 1

UI_STYLES = """
<style>
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  max-width: 960px;
  margin: 0 auto;
  padding: 24px;
  line-height: 1.5;
}
form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}
input, textarea {
  width: 100%;
  max-width: 720px;
  padding: 12px 14px;
  border: 1px solid #cfcfcf;
  border-radius: 10px;
  font-size: 16px;
  box-sizing: border-box;
}
textarea {
  min-height: 120px;
}
button {
  padding: 15px 25px;
  border: unset;
  border-radius: 15px;
  color: #212121;
  z-index: 1;
  background: #e8e8e8;
  position: relative;
  font-weight: 1000;
  font-size: 17px;
  -webkit-box-shadow: 4px 8px 19px -3px rgba(0,0,0,0.27);
  box-shadow: 4px 8px 19px -3px rgba(0,0,0,0.27);
  transition: all 250ms;
  overflow: hidden;
  cursor: pointer;
  width: fit-content;
}
button::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 0;
  border-radius: 15px;
  background-color: #212121;
  z-index: -1;
  -webkit-box-shadow: 4px 8px 19px -3px rgba(0,0,0,0.27);
  box-shadow: 4px 8px 19px -3px rgba(0,0,0,0.27);
  transition: all 250ms;
}
button:hover {
  color: #e8e8e8;
}
button:hover::before {
  width: 100%;
}
</style>
"""


def require_role(request: Request, role: str):
    if request.session.get("role") != role:
        return RedirectResponse(url="/", status_code=303)
    return None


def evaluate_submission(source_code: str, language_id: int, expected_output: str) -> dict[str, str]:
    payload = {
        "source_code": source_code,
        "language_id": language_id,
        "stdin": "",
        "expected_output": expected_output,
    }
    try:
        response = requests.post(
            f"{JUDGE0_URL}/submissions?base64_encoded=false&wait=true",
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "status": data.get("status", {}).get("description", "Unknown"),
            "stdout": data.get("stdout") or "",
            "stderr": data.get("stderr") or data.get("compile_output") or "",
        }
    except requests.RequestException as exc:
        return {"status": "Judge0 unavailable", "stdout": "", "stderr": str(exc)}


@app.get("/", response_class=HTMLResponse)
def login_page():
    return f"""
    <html><body>{UI_STYLES}
    <h1>Вход</h1>
    <form method='post' action='/login'>
      <input name='name' placeholder='Ваше имя' required />
      <button type='submit' name='role' value='teacher'>Я учитель</button>
      <button type='submit' name='role' value='student'>Я ученик</button>
    </form>
    </body></html>
    """


@app.post("/login")
def login(request: Request, name: str = Form(...), role: str = Form(...)):
    if role not in {"teacher", "student"}:
        return RedirectResponse(url="/", status_code=303)
    request.session["name"] = name
    request.session["role"] = role
    destination = "/teacher" if role == "teacher" else "/student"
    return RedirectResponse(url=destination, status_code=303)


@app.get("/teacher", response_class=HTMLResponse)
def teacher_page(request: Request):
    redirect = require_role(request, "teacher")
    if redirect:
        return redirect

    name = html.escape(request.session.get("name", "Учитель"))
    assignment_items = []
    for assignment in assignments:
        assignment_submissions = [s for s in submissions if s["assignment_id"] == assignment["id"]]
        rows = "".join(
            f"<li>{html.escape(s['student_name'])}: {html.escape(s['status'])}<pre>{html.escape(s['code'])}</pre>"
            f"<pre>{html.escape(s['stdout'])}</pre><pre>{html.escape(s['stderr'])}</pre></li>"
            for s in assignment_submissions
        )
        assignment_items.append(
            f"<li><b>{html.escape(assignment['title'])}</b>: {html.escape(assignment['description'])} "
            f"(expected: {html.escape(assignment['expected_output'])})<ul>{rows or '<li>Ответов пока нет</li>'}</ul></li>"
        )

    return f"""
    <html><body>{UI_STYLES}
    <h1>Панель учителя: {name}</h1>
    <a href='/'>Сменить роль</a>
    <h2>Добавить задание</h2>
    <form method='post' action='/teacher/assignments'>
      <input name='title' placeholder='Название задания' required />
      <textarea name='description' placeholder='Описание задания' required></textarea>
      <input name='expected_output' placeholder='Ожидаемый вывод (например 42)' value='' />
      <input type='number' name='language_id' value='71' min='1' required />
      <button type='submit'>Добавить</button>
    </form>
    <h2>Задания и ответы учеников</h2>
    <ul>{''.join(assignment_items) or '<li>Пока нет заданий</li>'}</ul>
    </body></html>
    """


@app.post("/teacher/assignments")
def add_assignment(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    expected_output: str = Form(""),
    language_id: int = Form(...),
):
    redirect = require_role(request, "teacher")
    if redirect:
        return redirect

    global assignment_id_seq
    assignments.append(
        {
            "id": assignment_id_seq,
            "title": title,
            "description": description,
            "expected_output": expected_output,
            "language_id": language_id,
        }
    )
    assignment_id_seq += 1
    return RedirectResponse(url="/teacher", status_code=303)


@app.get("/student", response_class=HTMLResponse)
def student_page(request: Request):
    redirect = require_role(request, "student")
    if redirect:
        return redirect

    name = html.escape(request.session.get("name", "Ученик"))
    cards = []
    for assignment in assignments:
        cards.append(
            f"""
            <li>
              <b>{html.escape(assignment['title'])}</b>: {html.escape(assignment['description'])}
              <form method='post' action='/student/submissions'>
                <input type='hidden' name='assignment_id' value='{assignment['id']}' />
                <textarea name='code' placeholder='Введите код' required></textarea>
                <button type='submit'>Отправить решение</button>
              </form>
            </li>
            """
        )

    return f"""
    <html><body>{UI_STYLES}
    <h1>Панель ученика: {name}</h1>
    <a href='/'>Сменить роль</a>
    <h2>Доступные задания</h2>
    <ul>{''.join(cards) or '<li>Пока нет заданий</li>'}</ul>
    </body></html>
    """


@app.post("/student/submissions")
def submit_solution(request: Request, assignment_id: int = Form(...), code: str = Form(...)):
    redirect = require_role(request, "student")
    if redirect:
        return redirect

    assignment = next((item for item in assignments if item["id"] == assignment_id), None)
    if assignment is None:
        return RedirectResponse(url="/student", status_code=303)

    global submission_id_seq
    result = evaluate_submission(code, assignment["language_id"], assignment["expected_output"])
    submissions.append(
        {
            "id": submission_id_seq,
            "assignment_id": assignment_id,
            "student_name": request.session.get("name", "Ученик"),
            "code": code,
            "status": result["status"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        }
    )
    submission_id_seq += 1
    return RedirectResponse(url="/student", status_code=303)
