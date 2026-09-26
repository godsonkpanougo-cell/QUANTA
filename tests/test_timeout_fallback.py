"""Test pour vérifier que le fallback PDF léger est appelé en cas de timeout."""

import pytest
from unittest.mock import patch, MagicMock
from subprocess import TimeoutExpired
import sys

import main
import db


def test_timeout_fallback_to_lightweight_pdf():
    """
    Test qu'un timeout du subprocess PDF Worker déclenche le fallback
    vers generate_lightweight_pdf() et retourne un PDF au lieu d'un 500.
    """
    # Nettoyer la base
    db.clear_all()
    
    # Créer un utilisateur de test
    user_id = db.create_or_update_user(
        "google-sub-timeout-test",
        "timeout-test@example.com",
        "Timeout Test User",
        "https://example.com/avatar.jpg",
    )
    
    # Créer une analyse terminée avec un résultat
    analysis_id = "test-analysis-timeout-123"
    file_id = "test-file-timeout-123"
    db.save_upload(
        file_id, user_id,
        {
            "path": "data/samples/clean.csv",
            "filename": "clean.csv",
            "numeric_cols": ["col1"],
            "cat_cols": [],
            "id_cols": [],
            "n_rows": 10,
            "n_cols": 1,
            "dataset_type": "tabular",
            "uploaded_at": "2024-01-01T00:00:00Z",
        }
    )
    
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    db.create_analysis(analysis_id, user_id, file_id, "Test query", now, file_hash="test_hash_123")
    
    # Simuler un résultat d'analyse
    result = {
        "confidence": {"score_global": 0.85},
        "tests": [{"name": "Test 1", "p_value": 0.05}],
        "interpretations": [{"test": "Test 1", "interpretation": "Significatif"}],
    }
    db.update_analysis(analysis_id, status="done", result=result, updated_at=now, user_id=user_id, file_hash="test_hash_123")
    
    # Mock subprocess.run pour lever TimeoutExpired
    with patch("main.subprocess.run") as mock_run:
        mock_run.side_effect = TimeoutExpired(
            ["python", "app/pdf_worker.py", "input", "output", "default"],
            timeout=300
        )
        
        # Mock generate_lightweight_pdf pour vérifier qu'il est appelé
        # La fonction est importée dynamiquement, donc on patche le module source
        with patch("app.report_generator.generate_lightweight_pdf") as mock_lightweight:
            mock_lightweight.return_value = b"%PDF-1.4 fake pdf content"
            
            # Créer un client de test
            from fastapi.testclient import TestClient
            client = TestClient(main.app)
            
            # Mock l'authentification
            def mock_get_current_user():
                return {"user_id": user_id}
            
            main.app.dependency_overrides[main.auth.get_current_user] = mock_get_current_user
            
            try:
                # Appeler l'endpoint /report
                response = client.get(f"/report/{analysis_id}")
                
                # Vérifier que generate_lightweight_pdf a été appelé
                assert mock_lightweight.called, "generate_lightweight_pdf devrait être appelé en cas de timeout"
                
                # Vérifier qu'un PDF est retourné (pas un 500)
                assert response.status_code == 200, f"Devrait retourner 200 avec PDF, pas {response.status_code}"
                assert response.headers["content-type"] == "application/pdf"
                assert b"PDF" in response.content
                
                print("TEST REUSSI: Timeout declenche le fallback PDF leger")
                
            finally:
                main.app.dependency_overrides.clear()
                db.clear_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
