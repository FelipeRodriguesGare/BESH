"""Authentication middleware for protecting endpoints."""

import os
import secrets
from typing import Optional
from fastapi import HTTPException, Depends, status, Request
from fastapi.security import HTTPBasic, HTTPBearer, HTTPAuthorizationCredentials

# Security schemes
security_basic = HTTPBasic()
security_bearer = HTTPBearer()


# Import config for credential lookup
def _get_credentials():
    """Get credentials from config or environment variables"""
    try:
        from besh.api.app import get_app_config

        config = get_app_config()
        return (
            config.basic_auth_username or os.environ.get("BASIC_AUTH_USERNAME"),
            config.basic_auth_password or os.environ.get("BASIC_AUTH_PASSWORD"),
            config.auth_api_key or os.environ.get("API_KEY"),
        )
    except:
        # Fallback to environment variables
        return (
            os.environ.get("BASIC_AUTH_USERNAME"),
            os.environ.get("BASIC_AUTH_PASSWORD"),
            os.environ.get("API_KEY"),
        )


class Auth:
    """Authentication utilities class."""
    
    @staticmethod
    def get_basic_auth_credentials():
        """Get basic auth credentials from config or environment."""
        username, password, _ = _get_credentials()
        return username, password
    
    @staticmethod
    def get_api_key():
        """Get API key from config or environment."""
        _, _, api_key = _get_credentials()
        return api_key
    
    @staticmethod
    def verify_basic_auth(username: str, password: str) -> bool:
        """Verify basic authentication credentials."""
        expected_username, expected_password = Auth.get_basic_auth_credentials()
        return secrets.compare_digest(
            username, expected_username
        ) and secrets.compare_digest(password, expected_password)
    
    @staticmethod
    def verify_api_key(api_key: str) -> bool:
        """Verify API key authentication."""
        expected_api_key = Auth.get_api_key()
        return secrets.compare_digest(api_key, expected_api_key)


async def verify_basic_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security_basic),
) -> dict:
    """FastAPI dependency to verify basic authentication."""
    if not Auth.verify_basic_auth(credentials.username, credentials.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return {"username": credentials.username}


async def verify_api_key(
    authorization: Optional[str] = Depends(security_bearer),
) -> str:
    """FastAPI dependency to verify API key authentication."""
    api_key = None
    
    # Check for API key in Authorization header (Bearer token)
    if authorization and authorization.credentials:
        api_key = authorization.credentials
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide via Authorization: Bearer <key> header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not Auth.verify_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return api_key


# Alternative dependency that checks multiple header formats
async def verify_api_key_flexible(request: Request) -> str:
    """FastAPI dependency to verify API key from multiple header formats."""
    
    # Check for API key in various headers
    api_key = (
        request.headers.get("X-API-Key")
        or request.headers.get("Api-Key")
        or (
            request.headers.get("Authorization", "").replace("Bearer ", "")
            if request.headers.get("Authorization", "").startswith("Bearer ")
            else None
        )
    )
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide via X-API-Key, Api-Key, or Authorization: Bearer <key> header.",
        )
    
    if not Auth.verify_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    
    return api_key
