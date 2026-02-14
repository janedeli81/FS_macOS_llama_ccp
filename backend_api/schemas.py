# schemas.py
"""
Pydantic schemas for request/response validation.
These define the structure of data sent to/from the API.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


# ============ Authentication Schemas ============

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: Optional[str] = None


# ============ User Schemas ============

class UserInfo(BaseModel):
    id: int
    email: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    trial_ends_at: Optional[datetime]
    documents_balance: int
    total_documents_purchased: int
    total_documents_used: int
    subscription_status: Optional[str]
    
    class Config:
        from_attributes = True


class UserStatus(BaseModel):
    """Quick status check for desktop app"""
    can_process: bool
    is_trial: bool
    trial_ends_at: Optional[datetime]
    documents_remaining: int
    subscription_active: bool


# ============ Payment Schemas ============

class PackagePurchase(BaseModel):
    package_type: str = Field(..., pattern="^(package_10|package_50|package_100)$")


class PaymentIntentResponse(BaseModel):
    client_secret: str
    amount: int
    currency: str = "usd"


class PaymentConfirm(BaseModel):
    payment_intent_id: str


# ============ Document Usage Schemas ============

class DocumentProcess(BaseModel):
    document_name: Optional[str] = None
    case_id: Optional[str] = None


class DocumentProcessResponse(BaseModel):
    success: bool
    remaining_balance: int
    was_trial: bool
    message: str


# ============ Transaction Schemas ============

class TransactionInfo(BaseModel):
    id: int
    amount: int
    currency: str
    status: str
    package_type: Optional[str]
    documents_count: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# ============ Error Response ============

class ErrorResponse(BaseModel):
    detail: str
