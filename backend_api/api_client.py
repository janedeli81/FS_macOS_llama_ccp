# backend/api_client.py
"""
API client for communication with FastAPI backend.
Handles authentication, payments, and document usage tracking.
"""

import requests
from typing import Optional, Dict, Any
from datetime import datetime


class APIClient:
    """Client for Forensic Summarizer backend API"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.session = requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authentication token"""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    # ============ Health Check ============

    def health_check(self) -> bool:
        """Check if backend is available"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False

    # ============ Authentication ============

    def register(self, email: str, password: str) -> Dict[str, Any]:
        """
        Register new user.
        Returns: {"success": bool, "token": str, "error": str}
        """
        try:
            response = self.session.post(
                f"{self.base_url}/auth/register",
                json={"email": email, "password": password},
                timeout=10
            )

            if response.status_code == 201:
                data = response.json()
                self.token = data["access_token"]
                return {"success": True, "token": self.token, "error": ""}
            else:
                error = response.json().get("detail", "Registration failed")
                return {"success": False, "token": "", "error": error}

        except Exception as e:
            return {"success": False, "token": "", "error": str(e)}

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Login user.
        Returns: {"success": bool, "token": str, "error": str}
        """
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                self.token = data["access_token"]
                return {"success": True, "token": self.token, "error": ""}
            else:
                error = response.json().get("detail", "Incorrect email or password")
                return {"success": False, "token": "", "error": error}

        except Exception as e:
            return {"success": False, "token": "", "error": str(e)}

    def set_token(self, token: str):
        """Set authentication token manually"""
        self.token = token

    # ============ User Info ============

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """Get current user profile"""
        try:
            response = self.session.get(
                f"{self.base_url}/users/me",
                headers=self._get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            return None

        except:
            return None

    def get_user_status(self) -> Optional[Dict[str, Any]]:
        """
        Get user status (trial, balance, etc.)
        Returns: {
            "can_process": bool,
            "is_trial": bool,
            "trial_ends_at": str,
            "documents_remaining": int,
            "subscription_active": bool
        }
        """
        try:
            response = self.session.get(
                f"{self.base_url}/users/status",
                headers=self._get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            return None

        except:
            return None

    # ============ Document Processing ============

    def process_document(self, document_name: str = "", case_id: str = "") -> Dict[str, Any]:
        """
        Deduct one document from balance.
        Call this BEFORE starting summarization.

        Returns: {
            "success": bool,
            "remaining_balance": int,
            "was_trial": bool,
            "message": str,
            "error": str
        }
        """
        try:
            response = self.session.post(
                f"{self.base_url}/documents/process",
                headers=self._get_headers(),
                json={"document_name": document_name, "case_id": case_id},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "remaining_balance": data["remaining_balance"],
                    "was_trial": data["was_trial"],
                    "message": data["message"],
                    "error": ""
                }
            else:
                error = response.json().get("detail", "Cannot process document")
                return {
                    "success": False,
                    "remaining_balance": 0,
                    "was_trial": False,
                    "message": "",
                    "error": error
                }

        except Exception as e:
            return {
                "success": False,
                "remaining_balance": 0,
                "was_trial": False,
                "message": "",
                "error": str(e)
            }

    # ============ Payments ============

    def create_payment_intent(self, package_type: str) -> Dict[str, Any]:
        """
        Create Stripe payment intent.

        Args:
            package_type: "package_10", "package_50", or "package_100"

        Returns: {
            "success": bool,
            "client_secret": str,
            "amount": int,
            "currency": str,
            "error": str
        }
        """
        try:
            response = self.session.post(
                f"{self.base_url}/payments/create-intent",
                headers=self._get_headers(),
                json={"package_type": package_type},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "client_secret": data["client_secret"],
                    "amount": data["amount"],
                    "currency": data["currency"],
                    "error": ""
                }
            else:
                error = response.json().get("detail", "Payment creation failed")
                return {
                    "success": False,
                    "client_secret": "",
                    "amount": 0,
                    "currency": "",
                    "error": error
                }

        except Exception as e:
            return {
                "success": False,
                "client_secret": "",
                "amount": 0,
                "currency": "",
                "error": str(e)
            }

    def confirm_payment(self, payment_intent_id: str) -> Dict[str, Any]:
        """
        Confirm payment and add documents to balance.

        Returns: {
            "success": bool,
            "documents_added": int,
            "new_balance": int,
            "error": str
        }
        """
        try:
            response = self.session.post(
                f"{self.base_url}/payments/confirm",
                headers=self._get_headers(),
                json={"payment_intent_id": payment_intent_id},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return {
                        "success": True,
                        "documents_added": data.get("documents_added", 0),
                        "new_balance": data.get("new_balance", 0),
                        "error": ""
                    }
                else:
                    return {
                        "success": False,
                        "documents_added": 0,
                        "new_balance": 0,
                        "error": data.get("message", "Payment not completed")
                    }
            else:
                error = response.json().get("detail", "Payment confirmation failed")
                return {
                    "success": False,
                    "documents_added": 0,
                    "new_balance": 0,
                    "error": error
                }

        except Exception as e:
            return {
                "success": False,
                "documents_added": 0,
                "new_balance": 0,
                "error": str(e)
            }