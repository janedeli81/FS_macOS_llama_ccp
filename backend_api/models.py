# models.py
"""
SQLAlchemy database models for users, subscriptions, and transactions.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from database import Base
from config import settings


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Trial period
    created_at = Column(DateTime, default=datetime.utcnow)
    trial_ends_at = Column(DateTime, nullable=True)
    
    # Document balance (pay-per-document model)
    documents_balance = Column(Integer, default=0)
    total_documents_purchased = Column(Integer, default=0)
    total_documents_used = Column(Integer, default=0)
    
    # Subscription (optional - for monthly plans)
    subscription_status = Column(String, nullable=True)  # active, canceled, past_due
    subscription_id = Column(String, nullable=True)  # Stripe subscription ID
    subscription_ends_at = Column(DateTime, nullable=True)
    
    # Relationships
    transactions = relationship("Transaction", back_populates="user")
    
    def is_trial_active(self) -> bool:
        """Check if user is still in trial period"""
        if not self.trial_ends_at:
            return False
        return datetime.utcnow() < self.trial_ends_at
    
    def can_process_document(self) -> bool:
        """Check if user can process a document (trial or has balance)"""
        return self.is_trial_active() or self.documents_balance > 0
    
    def deduct_document(self) -> bool:
        """
        Deduct one document from balance.
        Returns True if successful, False if insufficient balance.
        """
        if self.is_trial_active():
            self.total_documents_used += 1
            return True
        
        if self.documents_balance > 0:
            self.documents_balance -= 1
            self.total_documents_used += 1
            return True
        
        return False
    
    def add_documents(self, count: int):
        """Add documents to user's balance"""
        self.documents_balance += count
        self.total_documents_purchased += count


class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Stripe data
    stripe_payment_intent_id = Column(String, unique=True, nullable=True)
    stripe_charge_id = Column(String, nullable=True)
    
    # Transaction details
    amount = Column(Integer, nullable=False)  # in cents
    currency = Column(String, default="usd")
    status = Column(String, nullable=False)  # pending, completed, failed, refunded
    
    # Package info
    package_type = Column(String, nullable=True)  # package_10, package_50, package_100
    documents_count = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="transactions")


class UsageLog(Base):
    """Optional: Track individual document processing for analytics"""
    __tablename__ = "usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Document info
    document_name = Column(String, nullable=True)
    case_id = Column(String, nullable=True)
    
    # Usage details
    was_trial = Column(Boolean, default=False)
    processing_time_seconds = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
