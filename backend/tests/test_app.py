"""Tests for MalikSite1 application"""
import pathlib
import sys
import os
import pytest
import tempfile
from urllib.parse import urlparse, parse_qs, unquote_plus

# Add backend to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Create a temporary file for SQLite database during tests
test_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
test_db_file.close()
DB_PATH = f"sqlite:///{test_db_file.name}"

# Use file-based SQLite for testing (allows shared connections)
os.environ["DATABASE_URL"] = DB_PATH

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import after env setup
import app as web_app
from models import Base, Assignment, Submission, SubmissionStatus, User
import database

# Override the database to use our test configuration
def get_test_db():
    # Use the app's engine (which is now pointing to sqlite:///:memory:)
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Override the dependency
web_app.app.dependency_overrides[database.get_db] = get_test_db

# Create tables in the app's engine
Base.metadata.create_all(bind=database.engine)

client = TestClient(web_app.app)


@pytest.fixture(autouse=True)
def clear_session_and_reset_db():
    """Clear session cookies and reset database before each test"""
    # Create a new TestClient for each test to ensure fresh session
    global client
    client = TestClient(web_app.app)
    
    # Reset database
    Base.metadata.drop_all(bind=database.engine)
    Base.metadata.create_all(bind=database.engine)
    yield
    Base.metadata.drop_all(bind=database.engine)


@pytest.fixture(scope="session", autouse=True)
def cleanup_db():
    """Cleanup temporary database file after tests"""
    yield
    if os.path.exists(test_db_file.name):
        os.unlink(test_db_file.name)


def test_login_page_loads():
    """Test that login page loads successfully"""
    response = client.get("/")
    assert response.status_code == 200
    assert "MalikSite" in response.text or "Образовательная платформа" in response.text


def test_teacher_login():
    """Test teacher login"""
    response = client.post(
        "/login",
        data={"name": "Teacher", "access_code": "teacher123"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert "/teacher" in response.headers["location"]


def test_student_login():
    """Test student login"""
    response = client.post(
        "/login",
        data={"name": "Student", "access_code": "student123"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert "/student" in response.headers["location"]


def test_teacher_can_add_assignment():
    """Test that teacher can add an assignment"""
    # Login as teacher
    client.post(
        "/login",
        data={"name": "Teacher1", "access_code": "teacher123"},
    )
    
    # Add assignment
    response = client.post(
        "/teacher/assignments",
        data={
            "title": "Print 42",
            "description": "Output the number 42",
            "reference_code": "print(42)",
            "language_id": 71,
        },
        follow_redirects=False
    )
    assert response.status_code == 303
    
    # Check assignment appears on teacher page
    teacher_page = client.get("/teacher")
    assert "Print 42" in teacher_page.text
    assert "Output the number 42" in teacher_page.text


def test_student_can_view_assignments():
    """Test that student can view teacher's assignments"""
    # Teacher adds assignment
    client.post(
        "/login",
        data={"name": "Teacher2", "access_code": "teacher123"},
    )
    client.post(
        "/teacher/assignments",
        data={
            "title": "Echo Test",
            "description": "Print hello world",
            "reference_code": 'print("hello world")',
            "language_id": 71,
        },
    )
    
    # Student logs in and views assignments
    client.post(
        "/login",
        data={"name": "Student1", "access_code": "student123"},
    )
    student_page = client.get("/student")
    assert "Echo Test" in student_page.text
    assert "Print hello world" in student_page.text


def test_student_can_submit_code():
    """Test that student can submit code for evaluation"""
    # Teacher adds assignment
    client.post(
        "/login",
        data={"name": "Teacher3", "access_code": "teacher123"},
    )
    client.post(
        "/teacher/assignments",
        data={
            "title": "Simple Print",
            "description": "Print 42",
            "reference_code": "print(42)",
            "language_id": 71,
        },
    )
    
    # Student submits code
    client.post(
        "/login",
        data={"name": "Student2", "access_code": "student123"},
    )
    response = client.post(
        "/student/submissions",
        data={
            "assignment_id": 1,
            "code": 'print(42)',
        },
        follow_redirects=False
    )
    assert response.status_code == 303


def test_teacher_can_view_student_submissions():
    """Test that teacher can view student submissions"""
    # Teacher adds assignment
    client.post(
        "/login",
        data={"name": "Teacher4", "access_code": "teacher123"},
    )
    client.post(
        "/teacher/assignments",
        data={
            "title": "Test Task",
            "description": "Do something",
            "reference_code": 'print("result")',
            "language_id": 71,
        },
    )
    
    # Student submits code
    client.post(
        "/login",
        data={"name": "Student3", "access_code": "student123"},
    )
    client.post(
        "/student/submissions",
        data={
            "assignment_id": 1,
            "code": 'print("result")',
        },
    )
    
    # Teacher views submissions
    client.post(
        "/login",
        data={"name": "Teacher4", "access_code": "teacher123"},
    )
    teacher_page = client.get("/teacher")
    assert "Student3" in teacher_page.text
    assert 'print("result")' in teacher_page.text or "print" in teacher_page.text


def test_unauthorized_access_redirects():
    """Test that unauthorized access redirects to login"""
    response = client.get("/teacher", follow_redirects=False)
    assert response.status_code == 307 or response.status_code == 303


def test_teacher_can_create_code_assignment_with_tests():
    """Teacher can create code assignment with tests and limits"""
    client.post(
        "/login",
        data={"name": "Teacher5", "access_code": "teacher123"},
    )
    response = client.post(
        "/teacher/assignments",
        data={
            "title": "Sum A+B",
            "description": "Return sum",
            "reference_code": "a,b=map(int,input().split());print(a+b)",
            "expected_output": "",
            "language_id": 71,
            "is_code_assignment": "on",
            "tests_json": '[{"input":"2 3","expected_output":"5"}]',
            "time_limit": 3,
            "memory_limit": 512,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = database.SessionLocal()
    try:
        assignment = db.query(Assignment).filter(Assignment.title == "Sum A+B").first()
        assert assignment is not None
        assert assignment.is_code_assignment is True
        assert assignment.tests == [{"input": "2 3", "expected_output": "5"}]
        assert assignment.time_limit == 3
        assert assignment.memory_limit == 512
    finally:
        db.close()


def test_teacher_cannot_create_code_assignment_without_tests():
    """Code assignments must contain at least one test."""
    client.post(
        "/login",
        data={"name": "TeacherNoTests", "access_code": "teacher123"},
    )
    response = client.post(
        "/teacher/assignments",
        data={
            "title": "No tests assignment",
            "description": "desc",
            "reference_code": "print(1)",
            "expected_output": "",
            "language_id": 71,
            "is_code_assignment": "on",
            "tests_json": "[]",
            "time_limit": 2,
            "memory_limit": 256,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/teacher?form_error=" in response.headers["location"]

    query = parse_qs(urlparse(response.headers["location"]).query)
    message = unquote_plus(query["form_error"][0])
    assert "минимум один тест" in message

    db = database.SessionLocal()
    try:
        assignment = db.query(Assignment).filter(Assignment.title == "No tests assignment").first()
        assert assignment is None
    finally:
        db.close()


def test_teacher_cannot_create_code_assignment_with_invalid_tests_json():
    """Invalid tests_json should be rejected for code assignments."""
    client.post(
        "/login",
        data={"name": "TeacherBadJson", "access_code": "teacher123"},
    )
    response = client.post(
        "/teacher/assignments",
        data={
            "title": "Invalid JSON tests",
            "description": "desc",
            "reference_code": "print(1)",
            "expected_output": "",
            "language_id": 71,
            "is_code_assignment": "on",
            "tests_json": "{bad json",
            "time_limit": 2,
            "memory_limit": 256,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/teacher?form_error=" in response.headers["location"]

    query = parse_qs(urlparse(response.headers["location"]).query)
    message = unquote_plus(query["form_error"][0])
    assert "Невалидный JSON" in message

    db = database.SessionLocal()
    try:
        assignment = db.query(Assignment).filter(Assignment.title == "Invalid JSON tests").first()
        assert assignment is None
    finally:
        db.close()


def test_submit_code_api_returns_json_result(monkeypatch):
    """Code submission API returns structured verdict payload"""
    # Create assignment as teacher
    client.post(
        "/login",
        data={"name": "Teacher6", "access_code": "teacher123"},
    )
    client.post(
        "/teacher/assignments",
        data={
            "title": "Code API Task",
            "description": "desc",
            "reference_code": "print(1)",
            "language_id": 71,
            "is_code_assignment": "on",
            "tests_json": '[{"input":"","expected_output":"1"}]',
            "time_limit": 2,
            "memory_limit": 256,
        },
    )

    # Switch to student
    client.post(
        "/login",
        data={"name": "Student4", "access_code": "student123"},
    )

    def fake_eval_and_store_submission(db, assignment, student_id, code, language_id):
        class _Submission:
            id = 123

        return _Submission(), {
            "verdict": "Accepted",
            "details": "Accepted",
            "tests_passed": 1,
            "total_tests": 1,
        }

    monkeypatch.setattr(web_app, "evaluate_and_store_submission", fake_eval_and_store_submission)

    response = client.post(
        "/submit_code",
        json={
            "assignment_id": 1,
            "code": "print(1)",
            "language": "python",
        },
    )
    assert response.status_code == 200
    assert response.json()["verdict"] == "Accepted"
    assert response.json()["tests_passed"] == 1
    assert response.json()["total_tests"] == 1
    assert response.json()["submission_id"] == 123


def test_submit_code_api_no_tests_returns_helpful_message():
    """Student gets guidance when assignment has no tests configured."""
    client.post(
        "/login",
        data={"name": "TeacherNoTestsAPI", "access_code": "teacher123"},
    )
    db = database.SessionLocal()
    try:
        teacher = db.query(User).filter(User.name == "TeacherNoTestsAPI").first()
        assert teacher is not None
        assignment = Assignment(
            teacher_id=teacher.id,
            title="Broken code assignment",
            description="desc",
            reference_code="print(1)",
            expected_output="",
            language_id=71,
            is_code_assignment=True,
            tests=None,
            time_limit=2,
            memory_limit=256,
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        assignment_id = assignment.id
    finally:
        db.close()

    client.post(
        "/login",
        data={"name": "StudentNoTests", "access_code": "student123"},
    )
    response = client.post(
        "/submit_code",
        json={
            "assignment_id": assignment_id,
            "code": "print(1)",
            "language": "python",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["verdict"] == "No tests"
    assert "No tests configured for this assignment" in payload["details"]


def test_activity_api_without_submission_id_is_ignored():
    """Activity endpoint should not fail when submission_id is missing."""
    client.post(
        "/login",
        data={"name": "Student5", "access_code": "student123"},
    )
    response = client.post(
        "/api/activity",
        data={
            "activity_type": "focus_lost",
            "description": "Window lost focus",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_legacy_text_assignment_uses_description_input_and_expected_output(monkeypatch):
    """Legacy text assignment should parse stdin/expected output from description."""
    client.post(
        "/login",
        data={"name": "Teacher7", "access_code": "teacher123"},
    )
    client.post(
        "/teacher/assignments",
        data={
            "title": "Square Number",
            "description": "Найдите квадрат числа. Входные данные: 5 Ожидаемый вывод: 25",
            "reference_code": "",
            "expected_output": "",
            "language_id": 71,
        },
    )

    client.post(
        "/login",
        data={"name": "Student7", "access_code": "student123"},
    )

    def fake_eval_submission(source_code, language_id, expected_output="", stdin="", time_limit=2, memory_limit=256):
        assert stdin == "5"
        assert expected_output == "25"
        return {
            "status": SubmissionStatus.ACCEPTED.value,
            "stdout": "25",
            "stderr": "",
            "token": "fake-token",
            "time": "0.01",
            "memory": "1024",
        }

    monkeypatch.setattr(web_app, "evaluate_submission", fake_eval_submission)

    response = client.post(
        "/student/submissions",
        data={
            "assignment_id": 1,
            "code": "n=int(input());print(n*n)",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = database.SessionLocal()
    try:
        submission = db.query(Submission).first()
        assert submission is not None
        assert submission.status == SubmissionStatus.ACCEPTED.value
        assert submission.stdout == "25"
    finally:
        db.close()
