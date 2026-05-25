"""Database models for MalikSite1"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class User(Base):
    """User model for teachers and students"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # "teacher" or "student"
    created_at = Column(DateTime, default=datetime.utcnow)

    assignments = relationship("Assignment", back_populates="teacher")
    submissions = relationship("Submission", back_populates="student")
    activities = relationship("StudentActivity", back_populates="student")


class Assignment(Base):
    """Assignment model"""
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    expected_output = Column(Text, nullable=True)
    language_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    teacher = relationship("User", back_populates="assignments")
    submissions = relationship("Submission", back_populates="assignment", cascade="all, delete-orphan")


class SubmissionStatus(str, enum.Enum):
    """Status enum for submissions"""
    PENDING = "Pending"
    EVALUATING = "Evaluating"
    ACCEPTED = "Accepted"
    WRONG_ANSWER = "Wrong Answer"
    RUNTIME_ERROR = "Runtime Error"
    COMPILATION_ERROR = "Compilation Error"
    TIME_LIMIT_EXCEEDED = "Time Limit Exceeded"
    ERROR = "Error"


class Submission(Base):
    """Code submission model"""
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code = Column(Text, nullable=False)
    status = Column(String(50), default=SubmissionStatus.PENDING.value)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    judge0_token = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    evaluated_at = Column(DateTime, nullable=True)

    assignment = relationship("Assignment", back_populates="submissions")
    student = relationship("User", back_populates="submissions")


class ActivityType(str, enum.Enum):
    """Activity type enum"""
    FOCUS_LOST = "focus_lost"
    FOCUS_GAINED = "focus_gained"
    TAB_HIDDEN = "tab_hidden"
    TAB_VISIBLE = "tab_visible"
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    PAGE_UNLOAD = "page_unload"


class StudentActivity(Base):
    """Student activity tracking for academic integrity"""
    __tablename__ = "student_activities"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    activity_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_suspicious = Column(Boolean, default=False)

    student = relationship("User", back_populates="activities")
