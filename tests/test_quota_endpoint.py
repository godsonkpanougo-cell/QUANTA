"""Test empirique pour vérifier que GET /quota répond correctement."""

import pytest
from fastapi.testclient import TestClient
import main
import db


def test_quota_endpoint_returns_correct_data():
    """
    Test que GET /quota retourne les informations de quota correctement.
    """
    db.clear_all()
    
    # Créer un utilisateur
    user_id = db.create_or_update_user(
        "google-sub-quota-endpoint-test",
        "quota-endpoint@example.com",
        "Quota Endpoint Test",
        "https://example.com/avatar.jpg",
    )
    
    # Créer un client de test
    client = TestClient(main.app)
    
    # Mock l'authentification
    def mock_get_current_user():
        return {"user_id": user_id}
    
    main.app.dependency_overrides[main.auth.get_current_user] = mock_get_current_user
    
    try:
        # Appeler l'endpoint /quota
        response = client.get("/quota")
        
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Vérifier que la réponse est 200
        assert response.status_code == 200, f"GET /quota devrait retourner 200, pas {response.status_code}"
        
        # Vérifier que les données de quota sont présentes
        quota_data = response.json()
        assert "limit" in quota_data, "limit devrait être dans la réponse"
        assert "used" in quota_data, "used devrait être dans la réponse"
        assert "remaining" in quota_data, "remaining devrait être dans la réponse"
        
        # Vérifier les valeurs
        assert quota_data["limit"] == 15, "Le quota limite devrait être 15"
        assert quota_data["used"] == 0, "Le quota utilisé devrait être 0 pour un nouvel utilisateur"
        assert quota_data["remaining"] == 15, "Le quota restant devrait être 15 pour un nouvel utilisateur"
        
        print("TEST REUSSI: GET /quota retourne les données correctes")
        
    finally:
        main.app.dependency_overrides.clear()
        db.clear_all()


def test_quota_endpoint_with_existing_analyses():
    """
    Test que GET /quota retourne les bonnes valeurs après des analyses.
    """
    db.clear_all()
    
    # Créer un utilisateur
    user_id = db.create_or_update_user(
        "google-sub-quota-analyses-test",
        "quota-analyses@example.com",
        "Quota Analyses Test",
        "https://example.com/avatar.jpg",
    )
    
    # Simuler 5 analyses
    with db._get_conn() as conn:
        conn.execute(
            "UPDATE users SET analyses_count = 5 WHERE user_id = ?",
            (user_id,)
        )
    
    # Créer un client de test
    client = TestClient(main.app)
    
    # Mock l'authentification
    def mock_get_current_user():
        return {"user_id": user_id}
    
    main.app.dependency_overrides[main.auth.get_current_user] = mock_get_current_user
    
    try:
        # Appeler l'endpoint /quota
        response = client.get("/quota")
        
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Vérifier que la réponse est 200
        assert response.status_code == 200
        
        # Vérifier les valeurs
        quota_data = response.json()
        assert quota_data["used"] == 5, "Le quota utilisé devrait être 5"
        assert quota_data["remaining"] == 10, "Le quota restant devrait être 10"
        
        print("TEST REUSSI: GET /quota retourne les bonnes valeurs après analyses")
        
    finally:
        main.app.dependency_overrides.clear()
        db.clear_all()


def test_quota_endpoint_pre_migration_user():
    """
    Test que GET /quota initialise correctement les colonnes pour un utilisateur pré-migration.
    Simule un utilisateur créé avant l'ajout des colonnes analyses_count/quota_renewal_at
    en forçant ces colonnes à NULL après création.
    """
    db.clear_all()
    
    # Créer un utilisateur normalement
    user_id = db.create_or_update_user(
        "google-sub-pre-migration",
        "pre-migration@example.com",
        "Pre Migration",
        "https://example.com/avatar.jpg",
    )
    
    # Simuler un utilisateur pré-migration en forçant les colonnes quota à NULL
    # Note: on utilise une chaîne vide pour quota_renewal_at car SQLite peut avoir NOT NULL
    with db._get_conn() as conn:
        conn.execute(
            "UPDATE users SET analyses_count = NULL, quota_renewal_at = '' WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
    
    # Vérifier que les colonnes sont NULL/vides
    with db._get_conn() as conn:
        row = conn.execute(
            "SELECT analyses_count, quota_renewal_at FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        assert row is not None, "L'utilisateur devrait exister"
        assert row["analyses_count"] is None, "analyses_count devrait être NULL (pré-migration)"
        assert row["quota_renewal_at"] == "", "quota_renewal_at devrait être vide (pré-migration)"
    
    # Créer un client de test
    client = TestClient(main.app)
    
    # Mock l'authentification
    def mock_get_current_user():
        return {"user_id": user_id}
    
    main.app.dependency_overrides[main.auth.get_current_user] = mock_get_current_user
    
    try:
        # Appeler l'endpoint /quota
        response = client.get("/quota")
        
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Vérifier que la réponse est 200 (pas 404)
        assert response.status_code == 200, f"GET /quota devrait retourner 200 pour utilisateur pré-migration, pas {response.status_code}"
        
        # Vérifier que les données de quota sont présentes
        quota_data = response.json()
        assert "limit" in quota_data, "limit devrait être dans la réponse"
        assert "used" in quota_data, "used devrait être dans la réponse"
        assert "remaining" in quota_data, "remaining devrait être dans la réponse"
        assert "renewal_at" in quota_data, "renewal_at devrait être dans la réponse"
        
        # Vérifier les valeurs (devraient être initialisées par défaut)
        assert quota_data["limit"] == 15, "Le quota limite devrait être 15"
        assert quota_data["used"] == 0, "Le quota utilisé devrait être 0 (initialisé)"
        assert quota_data["remaining"] == 15, "Le quota restant devrait être 15 (initialisé)"
        assert quota_data["renewal_at"] != "", "renewal_at devrait être initialisé (non vide)"
        
        # Vérifier que les colonnes sont maintenant initialisées en base
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT analyses_count, quota_renewal_at FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            assert row["analyses_count"] == 0, "analyses_count devrait être initialisé à 0"
            assert row["quota_renewal_at"] is not None and row["quota_renewal_at"] != "", "quota_renewal_at devrait être initialisé"
        
        print("TEST REUSSI: GET /quota initialise correctement les colonnes pour utilisateur pré-migration")
        
    finally:
        main.app.dependency_overrides.clear()
        db.clear_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
