"""Tests pour le système de quota mensuel d'analyses."""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

import main
import db

# Utilisateur de test
TEST_USER_BASE = {
    "google_sub": "google-sub-quota-123",
    "email": "quota-test@example.com",
    "name": "Quota Test User",
    "picture_url": "https://example.com/avatar.jpg",
}

# Variable globale pour stocker le user_id actuel
CURRENT_TEST_USER_ID = None


def override_get_current_user():
    """Override pour simuler un utilisateur authentifié."""
    return {
        "user_id": CURRENT_TEST_USER_ID,
        **TEST_USER_BASE
    }


def test_quota_15_analyses_then_403():
    """
    Test que 15 analyses sont autorisées, mais la 16e est rejetée avec 403.
    """
    global CURRENT_TEST_USER_ID
    client = TestClient(main.app)
    
    main.app.dependency_overrides[main.auth.get_current_user] = override_get_current_user
    
    try:
        db.clear_all()
        
        # Créer l'utilisateur avec quota initialisé
        user_id = db.create_or_update_user(
            TEST_USER_BASE["google_sub"],
            TEST_USER_BASE["email"],
            TEST_USER_BASE["name"],
            TEST_USER_BASE["picture_url"],
        )
        
        # Mettre à jour la variable globale pour l'override
        CURRENT_TEST_USER_ID = user_id
        
        # Debug: vérifier les colonnes
        with db._get_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            print(f"  User row: {dict(row)}")
        
        # S'assurer que le quota est initialisé à 0
        with db._get_conn() as conn:
            conn.execute(
                "UPDATE users SET analyses_count = 0 WHERE user_id = ?",
                (user_id,)
            )
        
        # Uploader un fichier
        with open("data/samples/clean.csv", "rb") as f:
            upload_response = client.post("/upload", files={"file": ("test.csv", f, "text/csv")})
        
        assert upload_response.status_code == 200
        file_id = upload_response.json()["file_id"]
        
        # Lancer 15 analyses - toutes doivent réussir
        for i in range(15):
            analyze_response = client.post(
                "/analyze",
                json={"file_id": file_id, "query": "Test analysis"}
            )
            print(f"  Analyse {i+1}: {analyze_response.status_code}")
            assert analyze_response.status_code == 200, f"Analyse {i+1} devrait réussir"
        
        # La 16e analyse doit être rejetée avec 403
        analyze_response_16 = client.post(
            "/analyze",
            json={"file_id": file_id, "query": "Test analysis 16"}
        )
        print(f"  Analyse 16: {analyze_response_16.status_code}")
        assert analyze_response_16.status_code == 403, "16e analyse devrait être rejetée avec 403"
        assert "Quota mensuel atteint" in analyze_response_16.json()["detail"]
        
        print("TEST REUSSI: 15 analyses autorisees, 16e rejetee avec 403")
        
    finally:
        main.app.dependency_overrides.clear()
        db.clear_all()
        CURRENT_TEST_USER_ID = None


def test_quota_renewal_after_month():
    """
    Test que le quota est remis à zéro après un mois calendrier.
    Le renouvellement se produit automatiquement dans check_and_increment_quota.
    """
    global CURRENT_TEST_USER_ID
    client = TestClient(main.app)
    
    main.app.dependency_overrides[main.auth.get_current_user] = override_get_current_user
    
    try:
        db.clear_all()
        
        # Créer l'utilisateur
        user_id = db.create_or_update_user(
            TEST_USER_BASE["google_sub"],
            TEST_USER_BASE["email"],
            TEST_USER_BASE["name"],
            TEST_USER_BASE["picture_url"],
        )
        
        CURRENT_TEST_USER_ID = user_id
        
        # Simuler que le quota est épuisé et la date de renouvellement est passée
        past_date = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat() + "Z"
        with db._get_conn() as conn:
            conn.execute(
                "UPDATE users SET analyses_count = 15, quota_renewal_at = ? WHERE user_id = ?",
                (past_date, user_id)
            )
        
        # Vérifier directement dans la base que le compteur est à 15
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT analyses_count FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            assert row is not None
            assert row["analyses_count"] == 15, "Le compteur en base devrait être à 15 avant renouvellement"
        
        # Uploader un fichier
        with open("data/samples/clean.csv", "rb") as f:
            upload_response = client.post("/upload", files={"file": ("test.csv", f, "text/csv")})
        
        assert upload_response.status_code == 200
        file_id = upload_response.json()["file_id"]
        
        # Une analyse devrait être autorisée après renouvellement automatique
        # Le renouvellement se produit dans check_and_increment_quota pendant cet appel
        analyze_response = client.post(
            "/analyze",
            json={"file_id": file_id, "query": "Test after renewal"}
        )
        print(f"  Analyse après renouvellement: {analyze_response.status_code}")
        assert analyze_response.status_code == 200, "Analyse devrait être autorisée après renouvellement automatique"
        
        # Vérifier que le compteur a été incrémenté à 1 (après renouvellement automatique)
        quota_info_after = db.get_quota_info(user_id)
        assert quota_info_after["used"] == 1, "Le compteur devrait être incrémenté à 1 après renouvellement"
        assert quota_info_after["remaining"] == 14, "Le quota restant devrait être 14 après renouvellement"
        
        print("TEST REUSSI: Quota remis a zero apres un mois")
        
    finally:
        main.app.dependency_overrides.clear()
        db.clear_all()
        CURRENT_TEST_USER_ID = None


def test_quota_no_race_condition():
    """
    Test que plusieurs appels check_and_increment_quota en parallèle proche de la limite
    ne dépassent jamais 15 comptées au total.
    Test direct de la fonction DB pour éviter le rate limiting HTTP.
    """
    db.clear_all()
    
    # Créer l'utilisateur
    user_id = db.create_or_update_user(
        TEST_USER_BASE["google_sub"],
        TEST_USER_BASE["email"],
        TEST_USER_BASE["name"],
        TEST_USER_BASE["picture_url"],
    )
    
    # S'assurer que le quota est initialisé à 14 (proche de la limite)
    with db._get_conn() as conn:
        conn.execute(
            "UPDATE users SET analyses_count = 14 WHERE user_id = ?",
            (user_id,)
        )
    
    # Lancer 10 appels check_and_increment_quota en parallèle
    # Avec une transaction atomique, seul 1 devrait réussir (la 15e)
    import threading
    
    results = []
    def increment_quota():
        allowed, remaining, renewal = db.check_and_increment_quota(user_id)
        results.append(allowed)
    
    threads = []
    for i in range(10):
        t = threading.Thread(target=increment_quota)
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    # Compter les succès (True) et les rejets (False)
    success_count = sum(1 for allowed in results if allowed)
    reject_count = sum(1 for allowed in results if not allowed)
    
    print(f"  Succès: {success_count}, Rejets: {reject_count}")
    print(f"  Résultats: {results}")
    
    # Au total, on ne doit pas dépasser 15 analyses
    # On avait 14 avant + succès ici = max 15
    assert success_count <= 1, "Au plus 1 incrémentation parallèle devrait réussir (15e totale)"
    assert reject_count >= 9, "Au moins 9 incréments parallèles devraient être rejetés"
    
    # Vérifier le compteur final en base
    quota_info = db.get_quota_info(user_id)
    assert quota_info is not None
    assert quota_info["used"] == 15, "Le compteur final devrait être exactement 15"
    
    print("TEST REUSSI: Aucune race condition, compteur exactement 15")
    
    db.clear_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
