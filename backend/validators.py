"""Input validation and security utilities"""
import re
from typing import Tuple
from pydantic import BaseModel, Field, validator


class AssignmentCreate(BaseModel):
    """Validation model for creating assignments"""
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=5000)
    expected_output: str = Field(default="", max_length=5000)
    language_id: int = Field(...)
    
    @validator('title')
    def title_no_html(cls, v):
        """Prevent HTML injection in title"""
        if '<' in v or '>' in v or '&' in v:
            raise ValueError('Title cannot contain HTML characters')
        return v.strip()
    
    @validator('description')
    def description_no_script(cls, v):
        """Basic XSS prevention"""
        if '<script' in v.lower():
            raise ValueError('Description cannot contain script tags')
        return v.strip()
    
    @validator('language_id')
    def valid_language(cls, v):
        """Validate language ID"""
        valid_languages = [71, 62, 54]  # Python, Java, C++
        if v not in valid_languages:
            raise ValueError(f'Invalid language ID. Must be one of: {valid_languages}')
        return v


class CodeSubmission(BaseModel):
    """Validation model for code submission"""
    assignment_id: int = Field(..., gt=0)
    code: str = Field(..., min_length=1, max_length=100000)
    
    @validator('code')
    def code_not_empty(cls, v):
        """Ensure code is not just whitespace"""
        if not v.strip():
            raise ValueError('Code cannot be empty')
        return v


class UserLogin(BaseModel):
    """Validation model for user login"""
    name: str = Field(..., min_length=1, max_length=255)
    access_code: str = Field(..., min_length=1, max_length=255)
    
    @validator('name')
    def name_valid_chars(cls, v):
        """Validate name only contains safe characters"""
        if not re.match(r'^[а-яА-Яa-zA-Z0-9\s\-\.]+$', v):
            raise ValueError('Name contains invalid characters')
        return v.strip()


class ActivityLog(BaseModel):
    """Validation model for activity logging"""
    activity_type: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=1000)
    submission_id: int = Field(None, gt=0)
    
    @validator('activity_type')
    def valid_activity_type(cls, v):
        """Validate activity type"""
        valid_types = [
            'focus_lost',
            'focus_gained', 
            'tab_hidden',
            'tab_visible',
            'keyboard',
            'mouse',
            'page_unload'
        ]
        if v not in valid_types:
            raise ValueError(f'Invalid activity type. Must be one of: {valid_types}')
        return v


# Custom exception classes
class ValidationError(Exception):
    """Custom validation error"""
    pass


class Judge0Error(Exception):
    """Judge0 API error"""
    pass


class DatabaseError(Exception):
    """Database operation error"""
    pass


def validate_input(data: dict, model: BaseModel) -> Tuple[bool, str]:
    """
    Validate input data against Pydantic model
    Returns (is_valid, error_message)
    """
    try:
        model(**data)
        return True, ""
    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Validation error: {str(e)}"
