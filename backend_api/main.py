# main.py
"""
FastAPI backend for Forensic Summarizer application.
Handles authentication, payments, and document usage tracking.
"""

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
import stripe

from config import settings
from database import engine, Base, get_db
from models import User, Transaction, UsageLog
from schemas import (
    UserRegister, UserLogin, Token, UserInfo, UserStatus,
    PackagePurchase, PaymentIntentResponse, PaymentConfirm,
    DocumentProcess, DocumentProcessResponse, TransactionInfo
)
from auth import (
    get_password_hash, authenticate_user, create_access_token,
    get_current_active_user
)

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Forensic Summarizer API",
    description="Backend API for authentication and payment processing",
    version="1.0.0"
)

# Configure CORS for desktop app
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Health Check ============

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "message": "Forensic Summarizer API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "database": "connected",
        "stripe": "configured" if settings.STRIPE_SECRET_KEY else "not configured"
    }


# ============ Authentication Endpoints ============

@app.post("/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user with 7-day trial period.
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create new user with trial period
    trial_ends = datetime.utcnow() + timedelta(days=settings.TRIAL_PERIOD_DAYS)
    new_user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        trial_ends_at=trial_ends,
        is_active=True,
        is_verified=False  # Can implement email verification later
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Create access token
    access_token = create_access_token(data={"sub": new_user.email})

    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/auth/login", response_model=Token)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT token.
    """
    user = authenticate_user(db, user_data.email, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(data={"sub": user.email})

    return {"access_token": access_token, "token_type": "bearer"}


# ============ User Endpoints ============

@app.get("/users/me", response_model=UserInfo)
async def get_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get current user's profile information.
    """
    return current_user


@app.get("/users/status", response_model=UserStatus)
async def get_user_status(
    current_user: User = Depends(get_current_active_user)
):
    """
    Quick status check - used by desktop app before processing documents.
    """
    is_trial = current_user.is_trial_active()

    return {
        "can_process": current_user.can_process_document(),
        "is_trial": is_trial,
        "trial_ends_at": current_user.trial_ends_at,
        "documents_remaining": current_user.documents_balance,
        "subscription_active": current_user.subscription_status == "active"
    }


# ============ Payment Endpoints ============

@app.post("/payments/create-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    package: PackagePurchase,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a Stripe Payment Intent for purchasing document packages.
    """
    # Determine package details
    package_config = {
        "package_10": {"amount": settings.PACKAGE_10_PRICE, "documents": 10},
        "package_50": {"amount": settings.PACKAGE_50_PRICE, "documents": 50},
        "package_100": {"amount": settings.PACKAGE_100_PRICE, "documents": 100},
    }

    if package.package_type not in package_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid package type"
        )

    config = package_config[package.package_type]

    try:
        # Create Stripe Payment Intent
        intent = stripe.PaymentIntent.create(
            amount=config["amount"],
            currency=settings.CURRENCY,
            metadata={
                "user_id": current_user.id,
                "user_email": current_user.email,
                "package_type": package.package_type,
                "documents_count": config["documents"]
            }
        )

        # Create pending transaction record
        transaction = Transaction(
            user_id=current_user.id,
            stripe_payment_intent_id=intent.id,
            amount=config["amount"],
            currency=settings.CURRENCY,
            status="pending",
            package_type=package.package_type,
            documents_count=config["documents"]
        )
        db.add(transaction)
        db.commit()

        return {
            "client_secret": intent.client_secret,
            "amount": config["amount"],
            "currency": settings.CURRENCY
        }

    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stripe error: {str(e)}"
        )


@app.post("/payments/confirm")
async def confirm_payment(
    payment_data: PaymentConfirm,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Confirm payment and add documents to user's balance.
    """
    # Find transaction
    transaction = db.query(Transaction).filter(
        Transaction.stripe_payment_intent_id == payment_data.payment_intent_id,
        Transaction.user_id == current_user.id
    ).first()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )

    # Check payment status with Stripe
    try:
        intent = stripe.PaymentIntent.retrieve(payment_data.payment_intent_id)

        # TEST MODE: Allow requires_payment_method status for testing
        # In production, only "succeeded" should be accepted
        is_test_mode = settings.STRIPE_SECRET_KEY.startswith("sk_test_")
        allowed_statuses = ["succeeded"]

        if is_test_mode:
            # In test mode, also allow pending payments for easier testing
            allowed_statuses.extend(["requires_payment_method", "requires_confirmation", "processing"])

        if intent.status in allowed_statuses:
            # Update transaction
            transaction.status = "completed"
            transaction.completed_at = datetime.utcnow()
            transaction.stripe_charge_id = intent.latest_charge if intent.latest_charge else "test_charge"

            # Add documents to user's balance
            current_user.add_documents(transaction.documents_count)

            db.commit()

            return {
                "success": True,
                "documents_added": transaction.documents_count,
                "new_balance": current_user.documents_balance
            }
        else:
            return {
                "success": False,
                "status": intent.status,
                "message": f"Payment not completed (status: {intent.status})"
            }

    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stripe error: {str(e)}"
        )


# ============ Document Processing Endpoints ============

@app.post("/documents/process", response_model=DocumentProcessResponse)
async def process_document(
    doc_data: DocumentProcess,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Deduct one document from user's balance when processing.
    Desktop app should call this BEFORE starting summarization.
    """
    if not current_user.can_process_document():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient documents. Please purchase a package."
        )

    was_trial = current_user.is_trial_active()
    success = current_user.deduct_document()

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deduct document"
        )

    # Log usage (optional)
    usage_log = UsageLog(
        user_id=current_user.id,
        document_name=doc_data.document_name,
        case_id=doc_data.case_id,
        was_trial=was_trial
    )
    db.add(usage_log)
    db.commit()

    return {
        "success": True,
        "remaining_balance": current_user.documents_balance,
        "was_trial": was_trial,
        "message": "Document processing authorized"
    }


# ============ Transaction History ============

@app.get("/transactions", response_model=List[TransactionInfo])
async def get_transactions(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get user's transaction history.
    """
    transactions = db.query(Transaction).filter(
        Transaction.user_id == current_user.id
    ).order_by(Transaction.created_at.desc()).all()

    return transactions


# ============ Stripe Webhook (for production) ============

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Stripe webhooks for automated payment processing.
    This is called by Stripe when payment events occur.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle payment success
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]

        # Find and update transaction
        transaction = db.query(Transaction).filter(
            Transaction.stripe_payment_intent_id == payment_intent["id"]
        ).first()

        if transaction and transaction.status == "pending":
            transaction.status = "completed"
            transaction.completed_at = datetime.utcnow()

            # Add documents to user
            user = db.query(User).filter(User.id == transaction.user_id).first()
            if user:
                user.add_documents(transaction.documents_count)

            db.commit()

    return {"status": "success"}


# ============ Admin/Debug Endpoints (remove in production) ============

@app.get("/debug/users")
async def debug_list_users(db: Session = Depends(get_db)):
    """DEBUG: List all users (remove in production!)"""
    users = db.query(User).all()
    return [{"id": u.id, "email": u.email, "balance": u.documents_balance} for u in users]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
