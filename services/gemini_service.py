"""
Gemini Service Module for FINFLOW AI.
Provides reusable Gemini client handling, structured extraction, configurable models,
and connection testing with comprehensive error diagnostics.
"""

import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Ensure environment is loaded
load_dotenv()

DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


class GeminiService:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initializes GeminiService. Reads API key from parameter or environment variable securely.
        Never logs or exposes the full API key.
        """
        if api_key is not None:
            self.api_key = api_key.strip()
        else:
            self.api_key = os.getenv("GEMINI_API_KEY", "").strip()

        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self._client = None

    def get_client(self):
        """Lazily initializes and returns the Google GenAI client."""
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured or is empty.")
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def has_api_key(self) -> bool:
        """Returns True if an API key is present."""
        return bool(self.api_key)

    def get_masked_key(self) -> str:
        """Returns a masked representation of the API key for display/diagnostics."""
        if not self.api_key:
            return "Not Configured"
        if len(self.api_key) <= 8:
            return "••••••••"
        return f"{self.api_key[:4]}••••••••{self.api_key[-4:]}"

    def test_connection(self, prompt: str = "Hello FinFlow AI, respond with 'PONG'") -> Dict[str, Any]:
        """
        Tests the connection to the Gemini API.
        Returns a structured dictionary:
        {
            "status": "SUCCESS" | "MISSING_KEY" | "INVALID_KEY" | "QUOTA_EXHAUSTED" | "NETWORK_ERROR" | "MODEL_NOT_FOUND" | "SERVICE_UNAVAILABLE" | "ERROR",
            "message": User-friendly message,
            "response": Text response from Gemini if successful,
            "model": Model used,
            "error_detail": Technical error details (safe for logging)
        }
        """
        if not self.has_api_key():
            return {
                "status": "MISSING_KEY",
                "message": "Gemini API key is missing. Add GEMINI_API_KEY to your .env file or enter it in the sidebar.",
                "response": None,
                "model": self.model,
                "error_detail": "No API key found in environment or configuration.",
            }

        try:
            client = self.get_client()
            resp = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            reply = resp.text.strip() if resp and resp.text else ""
            return {
                "status": "SUCCESS",
                "message": f"Successfully connected to Google Gemini ({self.model})!",
                "response": reply,
                "model": self.model,
                "error_detail": None,
            }

        except Exception as e:
            err_str = str(e)
            err_type = type(e).__name__

            # Categorize the error
            if "11001" in err_str or "ConnectError" in err_type or "getaddrinfo failed" in err_str or "Network" in err_type:
                return {
                    "status": "NETWORK_ERROR",
                    "message": "Network error: Unable to reach Google API endpoints. Please check internet connection.",
                    "response": None,
                    "model": self.model,
                    "error_detail": f"Network resolution error: {err_str}",
                }
            elif "400" in err_str or "API_KEY_INVALID" in err_str or "invalid" in err_str.lower() and "key" in err_str.lower():
                return {
                    "status": "INVALID_KEY",
                    "message": "Invalid API key: Google rejected the provided GEMINI_API_KEY.",
                    "response": None,
                    "model": self.model,
                    "error_detail": err_str,
                }
            elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                return {
                    "status": "QUOTA_EXHAUSTED",
                    "message": "Gemini API quota exhausted (Rate limit 429). The platform will fall back gracefully to Demo Mode.",
                    "response": None,
                    "model": self.model,
                    "error_detail": err_str,
                }
            elif "404" in err_str or "NOT_FOUND" in err_str:
                return {
                    "status": "MODEL_NOT_FOUND",
                    "message": f"Model '{self.model}' was not found or is discontinued. Please select an available model (e.g. gemini-3.5-flash).",
                    "response": None,
                    "model": self.model,
                    "error_detail": err_str,
                }
            elif "503" in err_str or "UNAVAILABLE" in err_str:
                return {
                    "status": "SERVICE_UNAVAILABLE",
                    "message": f"Gemini model '{self.model}' is temporarily experiencing high demand (503). Retrying shortly or using mock fallback.",
                    "response": None,
                    "model": self.model,
                    "error_detail": err_str,
                }
            else:
                return {
                    "status": "ERROR",
                    "message": f"Gemini error: {err_type} - {err_str[:120]}",
                    "response": None,
                    "model": self.model,
                    "error_detail": err_str,
                }

    def generate_structured_invoice_extraction(self, prompt: str, schema_class):
        """Generates structured Pydantic extraction from Gemini with temperature 0.0."""
        from google.genai import types
        client = self.get_client()
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema_class,
                temperature=0.0,
            ),
        )
        return schema_class.model_validate_json(response.text)
