"""Test empirique pour vérifier si le bug datetime.utcnow() dans les sessions cause des déconnexions spontanées."""

import pytest
import db
from datetime import datetime, timedelta, timezone


def test_session_expiration_comparison():
    """
    Test que la comparaison d'expiration dans get_session() fonctionne correctement.
    Le bug potentiel : datetime.utcnow() (naive) vs dates stockées (timezone-aware).
    """
    db.clear_all()
    
    # Créer un utilisateur
    user_id = db.create_or_update_user(
        "google-sub-session-test",
        "session@example.com",
        "Session Test",
        "https://example.com/avatar.jpg",
    )
    
    # Créer une session
    session_token = db.create_session(user_id, ttl_hours=1)
    print(f"Session créée: {session_token}")
    
    # Vérifier que la session est valide immédiatement
    session = db.get_session(session_token)
    assert session is not None, "La session devrait être valide immédiatement après création"
    assert session["user_id"] == user_id
    print("Session valide immédiatement après création")
    
    # Vérifier que cleanup_expired_sessions() ne supprime pas les sessions valides
    deleted_count = db.cleanup_expired_sessions()
    assert deleted_count == 0, "cleanup_expired_sessions() ne devrait pas supprimer de sessions valides"
    print("cleanup_expired_sessions() ne supprime pas les sessions valides")
    
    # Vérifier que la session est toujours valide après cleanup
    session_after_cleanup = db.get_session(session_token)
    assert session_after_cleanup is not None, "La session devrait toujours être valide après cleanup"
    print("Session toujours valide après cleanup")
    
    db.clear_all()


def test_session_expiration_after_ttl():
    """
    Test qu'une session expirée est bien supprimée par get_session().
    """
    db.clear_all()
    
    # Créer un utilisateur
    user_id = db.create_or_update_user(
        "google-sub-expired-test",
        "expired@example.com",
        "Expired Test",
        "https://example.com/avatar.jpg",
    )
    
    # Créer une session avec TTL très court (1 seconde)
    session_token = db.create_session(user_id, ttl_hours=0.0003)  # ~1 seconde
    
    # Attendre un peu pour que la session expire
    import time
    time.sleep(2)
    
    # Vérifier que la session est expirée
    session = db.get_session(session_token)
    assert session is None, "La session devrait être expirée après TTL"
    print("Session expirée correctement détectée")
    
    db.clear_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
