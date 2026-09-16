"""
Tests d'authentification et d'isolation des données par utilisateur.
Utilise dependency_overrides pour simuler un utilisateur authentifié.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
import main
import db
from app import auth

# Utilisateur factice pour les tests
TEST_USER_A = {
    "user_id": "test_user_a",
    "email": "user_a@test.com",
    "name": "User A",
    "picture_url": "https://example.com/a.jpg",
}

TEST_USER_B = {
    "user_id": "test_user_b",
    "email": "user_b@test.com",
    "name": "User B",
    "picture_url": "https://example.com/b.jpg",
}


def override_get_current_user():
    """Override pour simuler un utilisateur authentifié (User A)."""
    return TEST_USER_A


def test_upload_without_auth_returns_401():
    """Test : /upload sans authentification renvoie 401."""
    client = TestClient(main.app)
    
    with open("data/samples/clean.csv", "rb") as f:
        response = client.post("/upload", files={"file": ("clean.csv", f, "text/csv")})
    
    assert response.status_code == 401
    assert response.json() == {"detail": "Non authentifié"}
    print("✓ TEST RÉUSSI: /upload sans authentification renvoie 401")


def test_analyze_without_auth_returns_401():
    """Test : /analyze sans authentification renvoie 401."""
    client = TestClient(main.app)
    
    response = client.post("/analyze", json={"file_id": "test_id", "query": "test"})
    
    assert response.status_code == 401
    assert response.json() == {"detail": "Non authentifié"}
    print("✓ TEST RÉUSSI: /analyze sans authentification renvoie 401")


def test_status_without_auth_returns_401():
    """Test : /status/{id} sans authentification renvoie 401."""
    client = TestClient(main.app)
    
    response = client.get("/status/test_analysis_id")
    
    assert response.status_code == 401
    assert response.json() == {"detail": "Non authentifié"}
    print("✓ TEST RÉUSSI: /status sans authentification renvoie 401")


def test_history_without_auth_returns_401():
    """Test : /history sans authentification renvoie 401."""
    client = TestClient(main.app)
    
    response = client.get("/history")
    
    assert response.status_code == 401
    assert response.json() == {"detail": "Non authentifié"}
    print("✓ TEST RÉUSSI: /history sans authentification renvoie 401")


def test_report_without_auth_returns_401():
    """Test : /report/{id} sans authentification renvoie 401."""
    client = TestClient(main.app)
    
    response = client.get("/report/test_analysis_id")
    
    assert response.status_code == 401
    assert response.json() == {"detail": "Non authentifié"}
    print("✓ TEST RÉUSSI: /report sans authentification renvoie 401")


def test_user_isolation_status_endpoint():
    """
    Test d'isolation : User A crée une analyse, User B tente d'y accéder via /status/{id},
    doit recevoir 404 (pas 403 pour ne pas confirmer l'existence).
    """
    client = TestClient(main.app)
    
    # Override pour User A
    main.app.dependency_overrides[auth.get_current_user] = lambda: TEST_USER_A
    
    try:
        db.clear_all()
        
        # User A crée un upload et une analyse
        file_id = "test_file_isolation"
        db.save_upload(file_id, TEST_USER_A["user_id"], {
            "path": "/tmp/test.csv",
            "filename": "test.csv",
            "numeric_cols": ["age"],
            "cat_cols": [],
            "id_cols": [],
            "n_rows": 10,
            "n_cols": 1,
            "dataset_type": "test",
            "uploaded_at": "2024-01-01T00:00:00Z",
        })
        
        analysis_id = "test_analysis_isolation"
        db.create_analysis(analysis_id, TEST_USER_A["user_id"], file_id, "test query", "2024-01-01T00:00:00Z")
        db.update_analysis(analysis_id, status="done", result={"test": "data"}, updated_at="2024-01-01T00:00:00Z", user_id=TEST_USER_A["user_id"])
        
        # User A peut accéder à l'analyse
        response = client.get(f"/status/{analysis_id}")
        assert response.status_code == 200
        assert response.json()["analysis_id"] == analysis_id
        
        # Override pour User B
        main.app.dependency_overrides[auth.get_current_user] = lambda: TEST_USER_B
        
        # User B ne peut pas accéder à l'analyse de User A (404)
        response = client.get(f"/status/{analysis_id}")
        assert response.status_code == 404
        assert "introuvable" in response.json()["detail"]
        
        print("✓ TEST RÉUSSI: isolation /status - User B ne peut pas voir l'analyse de User A")
        
    finally:
        main.app.dependency_overrides.clear()
        db.clear_all()


def test_user_isolation_report_endpoint():
    """
    Test d'isolation : User A crée une analyse, User B tente d'y accéder via /report/{id},
    doit recevoir 404.
    """
    client = TestClient(main.app)
    
    # Override pour User A
    main.app.dependency_overrides[auth.get_current_user] = lambda: TEST_USER_A
    
    try:
        db.clear_all()
        
        # User A crée un upload et une analyse
        file_id = "test_file_report_isolation"
        db.save_upload(file_id, TEST_USER_A["user_id"], {
            "path": "/tmp/test.csv",
            "filename": "test.csv",
            "numeric_cols": ["age"],
            "cat_cols": [],
            "id_cols": [],
            "n_rows": 10,
            "n_cols": 1,
            "dataset_type": "test",
            "uploaded_at": "2024-01-01T00:00:00Z",
        })
        
        analysis_id = "test_analysis_report_isolation"
        db.create_analysis(analysis_id, TEST_USER_A["user_id"], file_id, "test query", "2024-01-01T00:00:00Z")
        db.update_analysis(analysis_id, status="done", result={"test": "data"}, updated_at="2024-01-01T00:00:00Z", user_id=TEST_USER_A["user_id"])
        
        # Override pour User B
        main.app.dependency_overrides[auth.get_current_user] = lambda: TEST_USER_B
        
        # User B ne peut pas accéder au rapport de User A (404)
        response = client.get(f"/report/{analysis_id}")
        assert response.status_code == 404
        assert "introuvable" in response.json()["detail"]
        
        print("✓ TEST RÉUSSI: isolation /report - User B ne peut pas voir le rapport de User A")
        
    finally:
        main.app.dependency_overrides.clear()
        db.clear_all()


if __name__ == "__main__":
    print("=" * 60)
    print("TESTS D'AUTHENTIFICATION ET D'ISOLATION")
    print("=" * 60)
    
    test_upload_without_auth_returns_401()
    test_analyze_without_auth_returns_401()
    test_status_without_auth_returns_401()
    test_history_without_auth_returns_401()
    test_report_without_auth_returns_401()
    test_user_isolation_status_endpoint()
    test_user_isolation_report_endpoint()
    
    print("\n✓ TOUS LES TESTS D'AUTHENTIFICATION RÉUSSIS")
