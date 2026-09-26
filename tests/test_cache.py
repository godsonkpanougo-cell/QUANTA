"""Tests pour le système de cache d'analyses."""

import pytest
import db
import hashlib
from fastapi.testclient import TestClient
from main import app
import app.auth as auth


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Initialise et nettoie la base de données pour chaque test."""
    db.init_db()
    db.clear_all()
    yield
    db.clear_all()


def test_cache_hit_same_file_same_query():
    """Test qu'une analyse identique utilise le cache."""
    # Créer un utilisateur de test
    user_id = db.create_or_update_user(
        google_sub="cache-test-1",
        email="cache1@test.com",
        name="Cache Test 1",
        picture_url="http://example.com/avatar1.jpg",
    )
    
    # Créer un fichier temporaire pour le test
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("col1\n1\n2\n3\n")
        temp_file_path = f.name
    
    try:
        # Calculer le hash réel du fichier
        with open(temp_file_path, "rb") as f:
            file_bytes = f.read()
        real_hash = hashlib.sha256(file_bytes).hexdigest()
        
        # Créer un upload avec le chemin du fichier temporaire
        db.save_upload(
            file_id="cache-file-1",
            user_id=user_id,
            data={
                "path": temp_file_path,
                "filename": "test.csv",
                "numeric_cols": ["col1"],
                "cat_cols": [],
                "id_cols": [],
                "n_rows": 3,
                "n_cols": 1,
                "dataset_type": "cross-sectional",
                "uploaded_at": "2024-01-01T00:00:00Z",
            },
        )
        
        # Créer une première analyse terminée avec le hash réel
        analysis_id_1 = "cache-analysis-1"
        db.create_analysis(
            analysis_id=analysis_id_1,
            user_id=user_id,
            file_id="cache-file-1",
            query="test query",
            created_at="2024-01-01T00:00:00Z",
            file_hash=real_hash,
        )
        
        result_data = {"confidence": {"score_global": 0.85}, "tests": [{"name": "Test 1", "p_value": 0.05}]}
        db.update_analysis(
            analysis_id=analysis_id_1,
            status="done",
            result=result_data,
            updated_at="2024-01-01T00:00:00Z",
            user_id=user_id,
            file_hash=real_hash,
        )
        
        # Vérifier que find_cached_analysis trouve bien l'analyse
        cached = db.find_cached_analysis(user_id, real_hash, "test query")
        assert cached is not None, "find_cached_analysis devrait trouver l'analyse"
        assert cached["analysis_id"] == analysis_id_1
        
        # Mock l'authentification
        def mock_get_current_user():
            return {
                "user_id": user_id,
                "google_sub": "cache-test-1",
                "email": "cache1@test.com",
            }
        
        app.dependency_overrides[auth.get_current_user] = mock_get_current_user
        
        # Appeler /analyze avec le même fichier et la même requête
        response = client.post(
            "/analyze",
            json={"file_id": "cache-file-1", "query": "test query"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"
        assert data["from_cache"] == True
        assert "analysis_id" in data
        
        # Vérifier que le quota n'a PAS été décrémenté (car cache hit)
        quota_info = db.get_quota_info(user_id)
        assert quota_info["remaining"] == 15  # Quota intact
        
        # Vérifier que le résultat est le même
        new_analysis = db.get_analysis(data["analysis_id"], user_id)
        assert new_analysis["result"]["confidence"]["score_global"] == 0.85
        
    finally:
        app.dependency_overrides.clear()
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


def test_cache_miss_different_file():
    """Test qu'un fichier différent déclenche un recalcul."""
    # Créer un utilisateur de test
    user_id = db.create_or_update_user(
        google_sub="cache-test-2",
        email="cache2@test.com",
        name="Cache Test 2",
        picture_url="http://example.com/avatar2.jpg",
    )
    
    # Créer deux fichiers temporaires différents
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("col1\n1\n2\n3\n")
        temp_file_path_a = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("col1\n4\n5\n6\n")  # Contenu différent
        temp_file_path_b = f.name
    
    try:
        # Calculer les hash réels
        with open(temp_file_path_a, "rb") as f:
            hash_a = hashlib.sha256(f.read()).hexdigest()
        with open(temp_file_path_b, "rb") as f:
            hash_b = hashlib.sha256(f.read()).hexdigest()
        
        # Les hash doivent être différents
        assert hash_a != hash_b, "Les hash des fichiers différents doivent être différents"
        
        # Créer les uploads
        db.save_upload(
            file_id="cache-file-2a",
            user_id=user_id,
            data={
                "path": temp_file_path_a,
                "filename": "test_a.csv",
                "numeric_cols": ["col1"],
                "cat_cols": [],
                "id_cols": [],
                "n_rows": 3,
                "n_cols": 1,
                "dataset_type": "cross-sectional",
                "uploaded_at": "2024-01-01T00:00:00Z",
            },
        )
        
        db.save_upload(
            file_id="cache-file-2b",
            user_id=user_id,
            data={
                "path": temp_file_path_b,
                "filename": "test_b.csv",
                "numeric_cols": ["col1"],
                "cat_cols": [],
                "id_cols": [],
                "n_rows": 3,
                "n_cols": 1,
                "dataset_type": "cross-sectional",
                "uploaded_at": "2024-01-01T00:00:00Z",
            },
        )
        
        # Créer une analyse terminée pour le fichier A
        analysis_id_1 = "cache-analysis-2a"
        db.create_analysis(
            analysis_id=analysis_id_1,
            user_id=user_id,
            file_id="cache-file-2a",
            query="test query",
            created_at="2024-01-01T00:00:00Z",
            file_hash=hash_a,
        )
        
        db.update_analysis(
            analysis_id=analysis_id_1,
            status="done",
            result={"confidence": {"score_global": 0.85}},
            updated_at="2024-01-01T00:00:00Z",
            user_id=user_id,
            file_hash=hash_a,
        )
        
        # Vérifier que find_cached_analysis ne trouve PAS avec hash_b
        cached = db.find_cached_analysis(user_id, hash_b, "test query")
        assert cached is None, "find_cached_analysis ne devrait pas trouver avec un hash différent"
        
        # Mock l'authentification
        def mock_get_current_user():
            return {
                "user_id": user_id,
                "google_sub": "cache-test-2",
                "email": "cache2@test.com",
            }
        
        app.dependency_overrides[auth.get_current_user] = mock_get_current_user
        
        # Appeler /analyze avec le fichier B (hash différent)
        response = client.post(
            "/analyze",
            json={"file_id": "cache-file-2b", "query": "test query"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"  # Pas de cache hit
        assert data["from_cache"] == False
        
        # Vérifier que le quota a été décrémenté (cache miss)
        quota_info = db.get_quota_info(user_id)
        assert quota_info["remaining"] == 14  # Quota décrémenté
        
    finally:
        app.dependency_overrides.clear()
        if os.path.exists(temp_file_path_a):
            os.unlink(temp_file_path_a)
        if os.path.exists(temp_file_path_b):
            os.unlink(temp_file_path_b)


def test_cache_miss_different_query():
    """Test qu'une requête différente déclenche un recalcul."""
    # Créer un utilisateur de test
    user_id = db.create_or_update_user(
        google_sub="cache-test-3",
        email="cache3@test.com",
        name="Cache Test 3",
        picture_url="http://example.com/avatar3.jpg",
    )
    
    # Créer un fichier temporaire
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("col1\n1\n2\n3\n")
        temp_file_path = f.name
    
    try:
        # Calculer le hash réel
        with open(temp_file_path, "rb") as f:
            file_bytes = f.read()
        real_hash = hashlib.sha256(file_bytes).hexdigest()
        
        # Créer un upload
        db.save_upload(
            file_id="cache-file-3",
            user_id=user_id,
            data={
                "path": temp_file_path,
                "filename": "test.csv",
                "numeric_cols": ["col1"],
                "cat_cols": [],
                "id_cols": [],
                "n_rows": 3,
                "n_cols": 1,
                "dataset_type": "cross-sectional",
                "uploaded_at": "2024-01-01T00:00:00Z",
            },
        )
        
        # Créer une analyse terminée
        analysis_id_1 = "cache-analysis-3"
        db.create_analysis(
            analysis_id=analysis_id_1,
            user_id=user_id,
            file_id="cache-file-3",
            query="test query",
            created_at="2024-01-01T00:00:00Z",
            file_hash=real_hash,
        )
        
        db.update_analysis(
            analysis_id=analysis_id_1,
            status="done",
            result={"confidence": {"score_global": 0.85}},
            updated_at="2024-01-01T00:00:00Z",
            user_id=user_id,
            file_hash=real_hash,
        )
        
        # Vérifier que find_cached_analysis ne trouve PAS avec une requête différente
        cached = db.find_cached_analysis(user_id, real_hash, "different query")
        assert cached is None, "find_cached_analysis ne devrait pas trouver avec une requête différente"
        
        # Mock l'authentification
        def mock_get_current_user():
            return {
                "user_id": user_id,
                "google_sub": "cache-test-3",
                "email": "cache3@test.com",
            }
        
        app.dependency_overrides[auth.get_current_user] = mock_get_current_user
        
        # Appeler /analyze avec une requête différente
        response = client.post(
            "/analyze",
            json={"file_id": "cache-file-3", "query": "different query"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"  # Pas de cache hit
        assert data["from_cache"] == False
        
        # Vérifier que le quota a été décrémenté (cache miss)
        quota_info = db.get_quota_info(user_id)
        assert quota_info["remaining"] == 14  # Quota décrémenté
        
    finally:
        app.dependency_overrides.clear()
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


def test_cache_isolation_between_users():
    """Test que le cache est strictement isolé par utilisateur."""
    # Créer deux utilisateurs
    user_id_a = db.create_or_update_user(
        google_sub="cache-test-a",
        email="cachea@test.com",
        name="Cache Test A",
        picture_url="http://example.com/avatara.jpg",
    )
    
    user_id_b = db.create_or_update_user(
        google_sub="cache-test-b",
        email="cacheb@test.com",
        name="Cache Test B",
        picture_url="http://example.com/avatarb.jpg",
    )
    
    # Créer un fichier temporaire avec le même contenu pour les deux utilisateurs
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("col1\n1\n2\n3\n")
        temp_file_path_a = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("col1\n1\n2\n3\n")  # Même contenu
        temp_file_path_b = f.name
    
    try:
        # Calculer le hash (le même pour les deux fichiers)
        with open(temp_file_path_a, "rb") as f:
            shared_hash = hashlib.sha256(f.read()).hexdigest()
        
        # Créer les uploads pour les deux utilisateurs
        db.save_upload(
            file_id="cache-file-shared-a",
            user_id=user_id_a,
            data={
                "path": temp_file_path_a,
                "filename": "shared.csv",
                "numeric_cols": ["col1"],
                "cat_cols": [],
                "id_cols": [],
                "n_rows": 3,
                "n_cols": 1,
                "dataset_type": "cross-sectional",
                "uploaded_at": "2024-01-01T00:00:00Z",
            },
        )
        
        db.save_upload(
            file_id="cache-file-shared-b",
            user_id=user_id_b,
            data={
                "path": temp_file_path_b,
                "filename": "shared.csv",
                "numeric_cols": ["col1"],
                "cat_cols": [],
                "id_cols": [],
                "n_rows": 3,
                "n_cols": 1,
                "dataset_type": "cross-sectional",
                "uploaded_at": "2024-01-01T00:00:00Z",
            },
        )
        
        # Créer une analyse terminée pour l'utilisateur A
        analysis_id_a = "cache-analysis-a"
        db.create_analysis(
            analysis_id=analysis_id_a,
            user_id=user_id_a,
            file_id="cache-file-shared-a",
            query="test query",
            created_at="2024-01-01T00:00:00Z",
            file_hash=shared_hash,
        )
        
        db.update_analysis(
            analysis_id=analysis_id_a,
            status="done",
            result={"confidence": {"score_global": 0.85}},
            updated_at="2024-01-01T00:00:00Z",
            user_id=user_id_a,
            file_hash=shared_hash,
        )
        
        # Vérifier que l'utilisateur B ne trouve PAS le cache de l'utilisateur A
        cached_b = db.find_cached_analysis(user_id_b, shared_hash, "test query")
        assert cached_b is None, "find_cached_analysis ne devrait pas trouver le cache d'un autre utilisateur"
        
        # Mock l'authentification pour l'utilisateur B
        def mock_get_current_user_b():
            return {
                "user_id": user_id_b,
                "google_sub": "cache-test-b",
                "email": "cacheb@test.com",
            }
        
        app.dependency_overrides[auth.get_current_user] = mock_get_current_user_b
        
        # L'utilisateur B essaie d'analyser le même fichier avec la même requête
        # Il ne doit PAS utiliser le cache de l'utilisateur A
        response = client.post(
            "/analyze",
            json={"file_id": "cache-file-shared-b", "query": "test query"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"  # Pas de cache hit (isolation)
        assert data["from_cache"] == False
        
        # Vérifier que le quota de l'utilisateur B a été décrémenté
        quota_info_b = db.get_quota_info(user_id_b)
        assert quota_info_b["remaining"] == 14  # Quota décrémenté
        
    finally:
        app.dependency_overrides.clear()
        if os.path.exists(temp_file_path_a):
            os.unlink(temp_file_path_a)
        if os.path.exists(temp_file_path_b):
            os.unlink(temp_file_path_b)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
