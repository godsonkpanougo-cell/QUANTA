"""Test empirique pour vérifier que le même google_sub produit le même user_id à travers plusieurs connexions."""

import pytest
import db


def test_same_google_sub_same_user_id():
    """
    Preuve empirique : connecter le même utilisateur (même google_sub) deux fois
    doit retourner le même user_id. Si ce n'est pas le cas, l'historique disparaît
    à chaque déconnexion/reconnexion.
    """
    db.clear_all()
    
    google_sub = "google-sub-consistency-test"
    email = "consistency@example.com"
    name = "Consistency Test User"
    picture_url = "https://example.com/avatar.jpg"
    
    # Première connexion
    user_id_1 = db.create_or_update_user(google_sub, email, name, picture_url)
    print(f"Première connexion - user_id: {user_id_1}")
    
    # Deuxième connexion (même google_sub)
    user_id_2 = db.create_or_update_user(google_sub, email, name, picture_url)
    print(f"Deuxième connexion - user_id: {user_id_2}")
    
    # Vérifier que les user_id sont identiques
    assert user_id_1 == user_id_2, f"Le même google_sub devrait produire le même user_id: {user_id_1} != {user_id_2}"
    
    # Vérifier qu'il n'y a qu'un seul utilisateur en base
    with db._get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM users WHERE google_sub = ?", (google_sub,)).fetchall()
        assert len(rows) == 1, f"Il devrait y avoir exactement 1 utilisateur, mais il y en a {len(rows)}"
    
    print("TEST REUSSI: Même google_sub = même user_id (pas de duplication)")
    
    db.clear_all()


def test_different_google_sub_different_user_id():
    """
    Test que deux google_sub différents produisent deux user_id différents.
    """
    db.clear_all()
    
    # Premier utilisateur
    user_id_1 = db.create_or_update_user(
        "google-sub-1",
        "user1@example.com",
        "User 1",
        "https://example.com/avatar1.jpg",
    )
    
    # Deuxième utilisateur (google_sub différent)
    user_id_2 = db.create_or_update_user(
        "google-sub-2",
        "user2@example.com",
        "User 2",
        "https://example.com/avatar2.jpg",
    )
    
    # Vérifier que les user_id sont différents
    assert user_id_1 != user_id_2, "Deux google_sub différents devraient produire des user_id différents"
    
    # Vérifier qu'il y a deux utilisateurs en base
    with db._get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
        assert len(rows) == 2, f"Il devrait y avoir 2 utilisateurs, mais il y en a {len(rows)}"
    
    print("TEST REUSSI: Google_sub différents = user_id différents")
    
    db.clear_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
