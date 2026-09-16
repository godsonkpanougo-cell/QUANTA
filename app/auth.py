"""
Module d'authentification OAuth Google pour QUANTA.

Ce module contient :
- Configuration du client OAuth Google via Authlib
- Routes d'authentification (/auth/google, /auth/callback, /auth/logout, /auth/me)
- Dépendance get_current_user() pour protéger les endpoints

Version Authlib : 1.8.0 (choisie pour stabilité et absence de CVE connues majeures)
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import Response as FastAPIResponse
from authlib.integrations.starlette_client import OAuth

import db

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION OAUTH GOOGLE
# ═══════════════════════════════════════════════════════════════════════════════

# Configuration OAuth Google via Authlib
# Lit les credentials depuis les variables d'environnement
oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
    },
)

# Router FastAPI pour les routes d'authentification
router = APIRouter(prefix="/auth", tags=["auth"])


# ═══════════════════════════════════════════════════════════════════════════════
# DÉPENDANCE D'AUTHENTIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def get_current_user(session_token: str | None = Cookie(default=None)) -> dict[str, Any]:
    """
    Dépendance d'authentification : valide le session_token et retourne l'utilisateur.
    Lève HTTPException 401 si non authentifié ou session invalide.

    Args:
        session_token: Token de session extrait du cookie HTTP.

    Returns:
        dict: Informations de l'utilisateur (user_id, email, name, picture_url).

    Raises:
        HTTPException: 401 si non authentifié ou session invalide/expirée.
    """
    if session_token is None:
        raise HTTPException(status_code=401, detail="Non authentifié")

    session = db.get_session(session_token)
    if session is None:
        raise HTTPException(status_code=401, detail="Session invalide ou expirée")

    user = db.get_user_by_id(session["user_id"])
    if user is None:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")

    return user


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES D'AUTHENTIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/google")
async def auth_google(request: Request) -> Response:
    """
    Initie le flow OAuth Google en redirigeant l'utilisateur vers la page de connexion Google.

    Variables d'environnement requises :
        GOOGLE_REDIRECT_URI: URL de callback (ex: https://quanta-ijmg.onrender.com/auth/callback)

    Returns:
        Response: Redirection 302 vers Google OAuth.

    Raises:
        HTTPException: 500 si GOOGLE_REDIRECT_URI non configuré.
    """
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        raise HTTPException(status_code=500, detail="GOOGLE_REDIRECT_URI non configuré")

    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def auth_callback(request: Request) -> Response:
    """
    Callback OAuth Google : reçoit le code, échange le token, crée/màj l'utilisateur,
    crée la session, et redirige vers le frontend avec un cookie de session.

    Variables d'environnement requises :
        FRONTEND_URL: URL du frontend pour la redirection post-login (ex: https://quanta-statistic-goddess.vercel.app)

    Cookie de session :
        - httpOnly=True: Non accessible via JavaScript (sécurité XSS)
        - secure=True: Transmis uniquement via HTTPS
        - samesite="none": Nécessaire car backend et frontend sont sur des domaines différents
        - max_age: 7 jours

    Returns:
        Response: Redirection 302 vers FRONTEND_URL avec cookie de session.
    """
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        # Log côté serveur sans exposer de détails sensibles au client
        print(f"AUTH ERROR - Échec authorize_access_token : {e}", flush=True)
        return FastAPIResponse(status_code=302, headers={"Location": f"{frontend_url}?error=oauth_failed"})

    user_info = token.get("userinfo")
    if not user_info:
        print(f"AUTH ERROR - userinfo absent dans token", flush=True)
        return FastAPIResponse(status_code=302, headers={"Location": f"{frontend_url}?error=no_userinfo"})

    # Vérifier les champs retournés par Google
    google_sub = user_info.get("sub")
    email = user_info.get("email")
    name = user_info.get("name")
    picture_url = user_info.get("picture")

    if not google_sub or not email:
        print(f"AUTH ERROR - missing_user_data : sub={google_sub}, email={email}", flush=True)
        return FastAPIResponse(status_code=302, headers={"Location": f"{frontend_url}?error=missing_user_data"})

    # Créer ou mettre à jour l'utilisateur en base
    user_id = db.create_or_update_user(
        google_sub=google_sub,
        email=email,
        name=name,
        picture_url=picture_url,
    )

    # Créer la session
    session_token = db.create_session(user_id)

    # Rediriger vers le frontend avec cookie de session
    response = FastAPIResponse(status_code=302, headers={"Location": frontend_url})
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=60 * 60 * 24 * 7,  # 7 jours
    )
    return response


@router.post("/logout")
def logout(session_token: str | None = Cookie(default=None)) -> Response:
    """
    Déconnexion : supprime la session de la base et efface le cookie.

    Returns:
        Response: JSON avec message de confirmation et cookie supprimé.
    """
    if session_token:
        db.delete_session(session_token)

    response = FastAPIResponse(content='{"message": "Déconnecté"}', media_type="application/json")
    response.delete_cookie("session_token")
    return response


@router.get("/me")
def auth_me(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """
    Retourne les informations de l'utilisateur connecté.

    Returns:
        dict: user_id, email, name, picture_url.

    Raises:
        HTTPException: 401 si non authentifié (géré par get_current_user).
    """
    return {
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "name": current_user["name"],
        "picture_url": current_user["picture_url"],
    }
