from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, List
import tweepy

from ..database import users
from ..models.users import TwitterCredentials
from ..utils.auth import get_current_user_uid

router = APIRouter()

from datetime import datetime
import os

# Twitter API v2 configuration
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")

@router.get("/twitter/callback", response_class=HTMLResponse)
async def twitter_oauth_callback(
    request: Request,
    code: str,
    state: Optional[str] = None,
    code_verifier: Optional[str] = None
):
    """Handle Twitter OAuth callback and store credentials"""
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")
    
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Missing code_verifier")

    # Use state as uid since it was passed from the client
    uid = state

    try:
        # Initialize OAuth 2.0 client with PKCE
        oauth2_client = tweepy.OAuth2UserHandler(
            client_id=TWITTER_API_KEY,
            client_secret=TWITTER_API_SECRET,
            redirect_uri="https://api.omi.me/twitter/callback",
            scope=["tweet.read", "users.read", "dm.read"],
            code_verifier=code_verifier
        )
        
        # Exchange code for tokens
        token_data = oauth2_client.fetch_token(
            token_url="https://api.twitter.com/2/oauth2/token",
            code=code,
            code_verifier=code_verifier
        )

        # Get current timestamp for token creation time
        current_time = int(datetime.now().timestamp())
        
        twitter_creds = TwitterCredentials(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            expires_at=token_data.get("expires_at"),
            scope=token_data.get("scope"),
            token_type=token_data.get("token_type"),
            created_at=current_time
        )
        
        # Store credentials
        users.set_twitter_credentials(uid, twitter_creds.dict())

        # Return success page that redirects to app
        return """
        <html>
            <head>
                <title>Login Successful</title>
                <meta http-equiv="refresh" content="2;url=omiapp://">
            </head>
            <body>
                <h1>Twitter Login Successful!</h1>
                <p>Redirecting back to app...</p>
            </body>
        </html>
        """

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/twitter/dms", response_class=JSONResponse)
async def get_twitter_dms(
    uid: str = Depends(get_current_user_uid),
    max_results: int = 50,
    pagination_token: Optional[str] = None,
    conversation_id: Optional[str] = None,
    since_id: Optional[str] = None,
    until_id: Optional[str] = None
):
    """Fetch user's Twitter DMs using stored credentials"""
    try:
        # Get stored credentials
        creds = users.get_twitter_credentials(uid)
        if not creds:
            raise HTTPException(
                status_code=401,
                detail="Twitter credentials not found. Please connect Twitter account first."
            )

        # Initialize Twitter client
        client = tweepy.Client(
            bearer_token=creds['access_token'],
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_SECRET,
            wait_on_rate_limit=True
        )

        # Build query parameters
        params = {
            'max_results': max_results,
            'pagination_token': pagination_token,
        }
        if conversation_id:
            params['conversation_id'] = conversation_id
        if since_id:
            params['since_id'] = since_id
        if until_id:
            params['until_id'] = until_id

        # Check token expiration
        if creds.get('expires_at') and int(datetime.now().timestamp()) >= creds['expires_at']:
            # Token expired, try to refresh
            try:
                new_tokens = client.refresh_token(creds['refresh_token'])
                twitter_creds = TwitterCredentials(
                    access_token=new_tokens["access_token"],
                    refresh_token=new_tokens.get("refresh_token", creds['refresh_token']),
                    expires_at=new_tokens.get("expires_at"),
                    scope=new_tokens.get("scope", creds['scope']),
                    token_type=new_tokens.get("token_type", creds['token_type']),
                    created_at=int(datetime.now().timestamp())
                )
                users.set_twitter_credentials(uid, twitter_creds.dict())
                client = tweepy.Client(
                    bearer_token=twitter_creds.access_token,
                    consumer_key=TWITTER_API_KEY,
                    consumer_secret=TWITTER_API_SECRET,
                    wait_on_rate_limit=True
                )
            except Exception as e:
                users.delete_twitter_credentials(uid)
                raise HTTPException(
                    status_code=401,
                    detail="Twitter token expired and refresh failed. Please reconnect your account."
                )

        # Fetch DMs with filters
        dms = client.get_direct_messages(**params)
        
        # Format DM data
        formatted_dms = []
        for dm in dms.data or []:
            formatted_dms.append({
                'id': dm.id,
                'text': dm.text,
                'sender_id': dm.sender_id,
                'recipient_id': dm.recipient_id,
                'created_at': dm.created_at.isoformat() if dm.created_at else None,
                'conversation_id': dm.conversation_id
            })

        # Return formatted response with pagination info
        return {
            'messages': formatted_dms,
            'meta': {
                'result_count': len(formatted_dms),
                'next_token': dms.meta.get('next_token') if dms.meta else None,
                'previous_token': dms.meta.get('previous_token') if dms.meta else None
            }
        }

    except tweepy.TweepyException as e:
        if 'Unauthorized' in str(e):
            # Handle expired/invalid token
            users.delete_twitter_credentials(uid)
            raise HTTPException(
                status_code=401,
                detail="Twitter authorization expired. Please reconnect your account."
            )
        elif 'Rate limit exceeded' in str(e):
            raise HTTPException(
                status_code=429,
                detail="Twitter API rate limit exceeded. Please try again later."
            )
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
