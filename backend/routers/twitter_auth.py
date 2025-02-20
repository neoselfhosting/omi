from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import HTMLResponse
import tweepy
import os
import hashlib
import base64
import secrets
from datetime import datetime, timedelta
from typing import Dict, Tuple

from ..models.users import TwitterAuth

router = APIRouter()

# Twitter OAuth 2.0 settings
TWITTER_CLIENT_ID = os.getenv("TWITTER_CLIENT_ID")
TWITTER_CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET") 
TWITTER_REDIRECT_URI = os.getenv("TWITTER_REDIRECT_URI")

# Simple in-memory store for PKCE state
# In production, use Redis or another distributed cache
_pkce_states: Dict[str, Tuple[str, str]] = {}

def generate_code_verifier() -> str:
    """Generate a random code verifier for PKCE"""
    return secrets.token_urlsafe(32)

def generate_code_challenge(verifier: str) -> str:
    """Generate code challenge from verifier using S256 method"""
    sha256_hash = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(sha256_hash).decode().rstrip("=")

@router.get("/auth/twitter/authorize")
async def twitter_authorize(uid: str):
    """Initialize Twitter OAuth 2.0 flow with PKCE"""
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    
    # Generate state and store verifier
    state = secrets.token_urlsafe(32)
    _pkce_states[state] = (code_verifier, uid)
    
    oauth2_user_handler = tweepy.OAuth2UserHandler(
        client_id=TWITTER_CLIENT_ID,
        redirect_uri=TWITTER_REDIRECT_URI,
        scope=["tweet.read", "users.read", "dm.read"],
        code_challenge=code_challenge,
        code_challenge_method="S256"
    )
    
    auth_url = oauth2_user_handler.get_authorization_url(state=state)
    return {"auth_url": auth_url}

@router.get("/auth/twitter/callback", response_class=HTMLResponse)
async def twitter_callback(
    request: Request,
    code: str,
    state: str
):
    """Handle Twitter OAuth 2.0 callback with PKCE"""
    try:
        # Retrieve and validate state
        if state not in _pkce_states:
            raise HTTPException(status_code=400, detail="Invalid state parameter")
            
        code_verifier, uid = _pkce_states.pop(state)
        
        # Initialize OAuth 2.0 handler with code_verifier
        oauth2_user_handler = tweepy.OAuth2UserHandler(
            client_id=TWITTER_CLIENT_ID,
            client_secret=TWITTER_CLIENT_SECRET,
            redirect_uri=TWITTER_REDIRECT_URI,
            scope=["tweet.read", "users.read", "dm.read"],
            code_verifier=code_verifier
        )
        
        # Exchange code for access token
        access_token = oauth2_user_handler.fetch_token(
            code=code
        )
        
        # Store tokens in user model
        twitter_auth = TwitterAuth(
            uid=uid,
            access_token=access_token["access_token"],
            refresh_token=access_token.get("refresh_token"),
            expires_at=int((datetime.now() + 
                          timedelta(seconds=access_token["expires_in"])).timestamp())
        )
        
        # Save to database
        # TODO: Implement save_twitter_auth() in users.py
        
        # Return success page that redirects to app
        html_content = """
        <html>
            <head>
                <title>Twitter Login Success</title>
                <meta http-equiv="refresh" content="1;url=omiapp://">
            </head>
            <body>
                <h2>Login Successful!</h2>
                <p>Redirecting back to app...</p>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to complete Twitter authentication: {str(e)}"
        )
