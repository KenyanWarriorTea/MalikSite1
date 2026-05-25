"""Tests for MalikSite1 application"""
import pathlib
import sys
import os
import pytest
import tempfile

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
from models import Base
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
    assert "Вход в систему" in response.text


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
            "expected_output": "42\n",
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
            "expected_output": "hello world\n",
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
            "expected_output": "42\n",
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
            "expected_output": "result\n",
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
