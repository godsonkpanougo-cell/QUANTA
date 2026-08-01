"""Génère data/samples/french_excel_export.csv (Latin-1, ;, virgule décimale)."""
from pathlib import Path

rows = [
    ["id", "ville", "region", "satisfaction", "age", "revenu_annuel", "score"],
    ["1", "Paris, France", "Ile-de-France", "3", "35", "40035,33", "83,47"],
    ["2", "Lyon, France", "Auvergne-Rhone-Alpes", "4", "34", "60967,88", "87,88"],
    ["3", "Marseille, France", "Provence-Alpes-Cote d Azur", "5", "47", "62323,34", "79,35"],
    ["4", "Toulouse, France", "Occitanie", "2", "31", "53857,74", "78,23"],
    ["5", "Nice, France", "Provence-Alpes-Cote d Azur", "1", "54", "65985,26", "75,88"],
    ["6", "Nantes, France", "Pays de la Loire", "3", "28", "65648,39", "67,04"],
    ["7", "Strasbourg, France", "Grand Est", "4", "51", "55304,66", "67,25"],
    ["8", "Montpellier, France", "Occitanie", "2", "45", "83031,65", "70,29"],
    ["9", "Bordeaux, France", "Nouvelle-Aquitaine", "5", "56", "70696,04", "78,92"],
    ["10", "Lille, France", "Hauts-de-France", "3", "39", "48231,66", "79,68"],
    ["11", "Rennes, France", "Bretagne", "4", "43", "61387,92", "66,09"],
    ["12", "Reims, France", "Grand Est", "1", "24", "50110,70", "65,16"],
    ["13", "Grenoble, France", "Auvergne-Rhone-Alpes", "3", "46", "60796,02", "78,17"],
    ["14", "Dijon, France", "Bourgogne-Franche-Comte", "2", "62", "34448,35", "64,21"],
    ["15", "Angers, France", "Pays de la Loire", "5", "37", "55283,19", "87,88"],
    ["16", "Nimes, France", "Occitanie", "3", "56", "62735,08", "79,35"],
    ["17", "Tours, France", "Centre-Val de Loire", "4", "23", "59263,12", "78,23"],
    ["18", "Clermont-Ferrand, France", "Auvergne-Rhone-Alpes", "2", "60", "59879,64", "75,88"],
    ["19", "Le Havre, France", "Normandie", "1", "63", "48231,66", "67,04"],
    ["20", "Saint-Etienne, France", "Auvergne-Rhone-Alpes", "3", "50", "33497,50", "67,25"],
    ["21", "Toulon, France", "Provence-Alpes-Cote d Azur", "4", "22", "52391,48", "70,29"],
    ["22", "Perpignan, France", "Occitanie", "5", "49", "48252,67", "78,92"],
    ["23", "Besancon, France", "Bourgogne-Franche-Comte", "2", "43", "61394,73", "79,68"],
    ["24", "Orleans, France", "Centre-Val de Loire", "3", "44", "61387,92", "66,09"],
    ["25", "Metz, France", "Grand Est", "4", "24", "50110,70", "65,16"],
]

accent_map = {
    "Ile-de-France": "Île-de-France",
    "Auvergne-Rhone-Alpes": "Auvergne-Rhône-Alpes",
    "Provence-Alpes-Cote d Azur": "Provence-Alpes-Côte d'Azur",
    "Bourgogne-Franche-Comte": "Bourgogne-Franche-Comté",
}
for row in rows[1:]:
    row[2] = accent_map.get(row[2], row[2])
    if "Besancon" in row[1]:
        row[1] = "Besançon, France"
    if "Orleans" in row[1]:
        row[1] = "Orléans, France"

out = Path(__file__).resolve().parents[1] / "data" / "samples" / "french_excel_export.csv"
content = "\r\n".join(";".join(row) for row in rows) + "\r\n"
out.write_bytes(content.encode("latin-1"))
print(f"Written {out} ({out.stat().st_size} bytes)")
