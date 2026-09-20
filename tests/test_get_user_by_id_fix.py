"""Test empirique pour vérifier que get_user_by_id() fonctionne après correction du bug sqlite3.Row.get()."""

import pytest
import db


def test_get_user_by_id_returns_dict_with_quota_fields():
    """
    Test que get_user_by_id() retourne un dict avec analyses_count et quota_renewal_at
    sans lever AttributeError sur sqlite3.Row.get().
    """
    db.clear_all()
    
    # Créer un utilisateur
    user_id = db.create_or_update_user(
        "google-sub-test-fix",
        "test-fix@example.com",
        "Test Fix User",
        "https://example.com/avatar.jpg",
    )
    
    # Récupérer l'utilisateur via get_user_by_id
    user = db.get_user_by_id(user_id)
    
    # Vérifier que c'est un dict
    assert user is not None, "L'utilisateur devrait exister"
    assert isinstance(user, dict), "get_user_by_id devrait retourner un dict"
    
    # Vérifier les champs de quota
    assert "analyses_count" in user, "analyses_count devrait être dans le dict"
    assert "quota_renewal_at" in user, "quota_renewal_at devrait être dans le dict"
    
    # Vérifier les valeurs par défaut
    assert user["analyses_count"] == 0, "analyses_count devrait être 0 par défaut"
    assert user["quota_renewal_at"] != "", "quota_renewal_at devrait être initialisé"
    
    # Vérifier les autres champs
    assert user["user_id"] == user_id
    assert user["email"] == "test-fix@example.com"
    assert user["name"] == "Test Fix User"
    
    print("TEST REUSSI: get_user_by_id() retourne un dict correct avec champs quota")
    
    db.clear_all()


def test_get_user_by_id_with_existing_quota():
    """
    Test que get_user_by_id() lit correctement les valeurs de quota existantes.
    """
    db.clear_all()
    
    # Créer un utilisateur
    user_id = db.create_or_update_user(
        "google-sub-test-quota",
        "test-quota@example.com",
        "Test Quota User",
        "https://example.com/avatar.jpg",
    )
    
    # Modifier manuellement le quota
    with db._get_conn() as conn:
        conn.execute(
            "UPDATE users SET analyses_count = 5 WHERE user_id = ?",
            (user_id,)
        )
    
    # Récupérer l'utilisateur
    user = db.get_user_by_id(user_id)
    
    # Vérifier que la valeur est lue correctement
    assert user is not None
    assert user["analyses_count"] == 5, "analyses_count devrait être 5"
    
    print("TEST REUSSI: get_user_by_id() lit correctement les valeurs de quota existantes")
    
    db.clear_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
