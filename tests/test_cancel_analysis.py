"""Tests pour l'endpoint d'annulation d'analyse."""

import pytest
from fastapi.testclient import TestClient
from main import app
import db
import app.auth as auth

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Initialise et nettoie la base de données pour chaque test."""
    db.init_db()
    db.clear_all()
    yield
    db.clear_all()


def test_cancel_analysis_running():
    """Test l'annulation d'une analyse en cours."""
    # Créer un utilisateur de test
    user_id = db.create_or_update_user(
        google_sub="google-cancel",
        email="cancel@test.com",
        name="Cancel Test",
        picture_url="http://example.com/avatar.jpg",
    )
    
    # Créer un upload
    db.save_upload(
        file_id="test-cancel-file",
        user_id=user_id,
        data={
            "path": "/tmp/test.csv",
            "filename": "test.csv",
            "numeric_cols": ["col1"],
            "cat_cols": ["col2"],
            "id_cols": [],
            "n_rows": 100,
            "n_cols": 2,
            "dataset_type": "cross-sectional",
            "uploaded_at": "2024-01-01T00:00:00Z",
        },
    )
    
    # Créer une analyse en cours
    db.create_analysis(
        analysis_id="test-cancel-analysis",
        user_id=user_id,
        file_id="test-cancel-file",
        query="test query",
        created_at="2024-01-01T00:00:00Z",
        file_hash="cancel_hash_1",
    )
    
    # Mettre à jour le statut à "running"
    db.update_analysis(
        analysis_id="test-cancel-analysis",
        status="running",
        updated_at="2024-01-01T00:00:00Z",
        user_id=user_id,
        file_hash="cancel_hash_1",
    )
    
    # Mock l'authentification
    def mock_get_current_user():
        return {
            "user_id": user_id,
            "google_sub": "google-cancel",
            "email": "cancel@test.com",
        }
    
    app.dependency_overrides[auth.get_current_user] = mock_get_current_user
    
    try:
        # Appeler l'endpoint d'annulation
        response = client.post("/analyses/test-cancel-analysis/cancel")
        
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_id"] == "test-cancel-analysis"
        assert data["status"] == "cancelled"
        
        # Vérifier que le statut a été mis à jour en base
        analysis = db.get_analysis("test-cancel-analysis", user_id)
        assert analysis["status"] == "cancelled"
    finally:
        app.dependency_overrides.clear()


def test_cancel_analysis_already_done():
    """Test que l'annulation échoue pour une analyse déjà terminée."""
    # Créer un utilisateur de test
    user_id = db.create_or_update_user(
        google_sub="google-cancel-2",
        email="cancel2@test.com",
        name="Cancel Test 2",
        picture_url="http://example.com/avatar2.jpg",
    )
    
    # Créer un upload
    db.save_upload(
        file_id="test-cancel-file-2",
        user_id=user_id,
        data={
            "path": "/tmp/test2.csv",
            "filename": "test2.csv",
            "numeric_cols": ["col1"],
            "cat_cols": ["col2"],
            "id_cols": [],
            "n_rows": 100,
            "n_cols": 2,
            "dataset_type": "cross-sectional",
            "uploaded_at": "2024-01-01T00:00:00Z",
        },
    )
    
    # Créer une analyse terminée
    db.create_analysis(
        analysis_id="test-cancel-analysis-2",
        user_id=user_id,
        file_id="test-cancel-file-2",
        query="test query",
        created_at="2024-01-01T00:00:00Z",
        file_hash="cancel_hash_2",
    )
    
    # Mettre à jour le statut à "done"
    db.update_analysis(
        analysis_id="test-cancel-analysis-2",
        status="done",
        updated_at="2024-01-01T00:00:00Z",
        user_id=user_id,
        file_hash="cancel_hash_2",
    )
    
    # Mock l'authentification
    def mock_get_current_user():
        return {
            "user_id": user_id,
            "google_sub": "google-cancel-2",
            "email": "cancel2@test.com",
        }
    
    app.dependency_overrides[auth.get_current_user] = mock_get_current_user
    
    try:
        # Appeler l'endpoint d'annulation
        response = client.post("/analyses/test-cancel-analysis-2/cancel")
        
        assert response.status_code == 400
        assert "Impossible d'annuler" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_cancel_analysis_not_found():
    """Test que l'annulation échoue pour une analyse inexistante."""
    # Mock l'authentification
    def mock_get_current_user():
        return {
            "user_id": "test-cancel-user-3",
            "google_sub": "google-cancel-3",
            "email": "cancel3@test.com",
        }
    
    app.dependency_overrides[auth.get_current_user] = mock_get_current_user
    
    try:
        # Appeler l'endpoint d'annulation
        response = client.post("/analyses/non-existent-analysis/cancel")
        
        assert response.status_code == 404
        assert "introuvable" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_cancel_analysis_wrong_user():
    """Test que l'annulation échoue pour une analyse appartenant à un autre utilisateur."""
    # Créer deux utilisateurs
    user_id_4 = db.create_or_update_user(
        google_sub="google-cancel-4",
        email="cancel4@test.com",
        name="Cancel Test 4",
        picture_url="http://example.com/avatar4.jpg",
    )
    
    user_id_5 = db.create_or_update_user(
        google_sub="google-cancel-5",
        email="cancel5@test.com",
        name="Cancel Test 5",
        picture_url="http://example.com/avatar5.jpg",
    )
    
    # Créer un upload pour l'utilisateur 4
    db.save_upload(
        file_id="test-cancel-file-4",
        user_id=user_id_4,
        data={
            "path": "/tmp/test4.csv",
            "filename": "test4.csv",
            "numeric_cols": ["col1"],
            "cat_cols": ["col2"],
            "id_cols": [],
            "n_rows": 100,
            "n_cols": 2,
            "dataset_type": "cross-sectional",
            "uploaded_at": "2024-01-01T00:00:00Z",
        },
    )
    
    # Créer une analyse pour l'utilisateur 4
    db.create_analysis(
        analysis_id="test-cancel-analysis-4",
        user_id=user_id_4,
        file_id="test-cancel-file-4",
        query="test query",
        created_at="2024-01-01T00:00:00Z",
        file_hash="cancel_hash_4",
    )
    
    # Mettre à jour le statut à "running"
    db.update_analysis(
        analysis_id="test-cancel-analysis-4",
        status="running",
        updated_at="2024-01-01T00:00:00Z",
        user_id=user_id_4,
        file_hash="cancel_hash_4",
    )
    
    # Mock l'authentification pour l'utilisateur 5
    def mock_get_current_user():
        return {
            "user_id": user_id_5,
            "google_sub": "google-cancel-5",
            "email": "cancel5@test.com",
        }
    
    app.dependency_overrides[auth.get_current_user] = mock_get_current_user
    
    try:
        # L'utilisateur 5 essaie d'annuler l'analyse de l'utilisateur 4
        response = client.post("/analyses/test-cancel-analysis-4/cancel")
        
        assert response.status_code == 404
        assert "introuvable" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
