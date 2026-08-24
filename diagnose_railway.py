"""Script de diagnostic pour vérifier la configuration Railway"""
import os
import requests
import json

# Remplacez par votre URL Railway
RAILWAY_URL = os.environ.get("RAILWAY_URL", "https://votre-app.railway.app")

print(f"=== Diagnostic QUANTA Railway ===")
print(f"URL cible: {RAILWAY_URL}")
print()

# 1. Vérifier si le serveur répond
try:
    response = requests.get(f"{RAILWAY_URL}/", timeout=10)
    print(f"✅ Serveur répond: HTTP {response.status_code}")
except Exception as e:
    print(f"❌ Serveur inaccessible: {e}")
    exit(1)

# 2. Vérifier l'historique des analyses
try:
    response = requests.get(f"{RAILWAY_URL}/history", timeout=10)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Historique accessible: {data.get('count', 0)} analyses")
        if data.get('analyses'):
            latest = data['analyses'][0]
            print(f"   Dernière analyse: {latest.get('analysis_id')} - statut: {latest.get('status')}")
    else:
        print(f"❌ Historique inaccessible: HTTP {response.status_code}")
except Exception as e:
    print(f"❌ Erreur historique: {e}")

# 3. Vérifier une analyse existante (si disponible)
print()
print("=== Instructions pour tester ===")
print("1. Uploader un fichier CSV sur votre instance Railway")
print("2. Lancer une analyse")
print("3. Copier l'analysis_id")
print("4. Exécuter: python diagnose_railway.py <analysis_id>")
print()
print("Ou vérifiez les logs Railway pour:")
print("   - 'Matplotlib backend: Agg'")
print("   - 'Generated X charts'")
print("   - 'CHARTS DEBUG' messages")
