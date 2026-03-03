import pathlib
import sys

from fastapi.testclient import TestClient

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import app as web_app


client = TestClient(web_app.app)


def setup_function():
    web_app.assignments.clear()
    web_app.submissions.clear()
    web_app.assignment_id_seq = 1
    web_app.submission_id_seq = 1


def test_teacher_can_add_assignment_and_view_it():
    response = client.post("/login", data={"name": "Teacher", "role": "teacher"})
    assert response.status_code == 200

    response = client.post(
        "/teacher/assignments",
        data={
            "title": "Print 42",
            "description": "Output number",
            "expected_output": "42\n",
            "language_id": 71,
        },
    )
    assert response.status_code == 200

    page = client.get("/teacher")
    assert "Print 42" in page.text


def test_student_submission_is_visible_for_teacher(monkeypatch):
    client.post("/login", data={"name": "Teacher", "role": "teacher"})
    client.post(
        "/teacher/assignments",
        data={
            "title": "Echo",
            "description": "Print hello",
            "expected_output": "hello\n",
            "language_id": 71,
        },
    )

    def fake_eval(code, language_id, expected_output):
        assert code == 'print("hello")'
        assert language_id == 71
        assert expected_output == "hello\n"
        return {"status": "Accepted", "stdout": "hello\n", "stderr": ""}

    monkeypatch.setattr(web_app, "evaluate_submission", fake_eval)

    client.post("/login", data={"name": "Student", "role": "student"})
    submit = client.post(
        "/student/submissions",
        data={"assignment_id": 1, "code": 'print("hello")'},
    )
    assert submit.status_code == 200

    client.post("/login", data={"name": "Teacher", "role": "teacher"})
    teacher_page = client.get("/teacher")
    assert "Student" in teacher_page.text
    assert "Accepted" in teacher_page.text
    assert 'print(&quot;hello&quot;)' in teacher_page.text
