"""Test manuel pour vérifier l'ACP avec colonne ID numérique."""
import json
from app.compute.upload_validation import load_and_diagnose
from app.compute.compute import run_base_compute_pipeline
from app.compute.test_selector import select_and_run_test
from app.orchestrator import _resolve_delegation
from app.llm.brain import AnalysisIntent

def test_acp_with_numeric_id():
    """Test avec colonne ID numérique (test_acp_numeric_id.csv)."""
    print("=== TEST 2 : Dataset avec colonne ID numérique (test_acp_numeric_id.csv) ===")
    
    with open("tests/test_acp_numeric_id.csv", "rb") as f:
        file_bytes = f.read()
    
    # Diagnostic
    diag = load_and_diagnose(file_bytes, "test_acp_numeric_id.csv")
    print(f"id_cols: {diag['id_cols']}")
    print(f"numeric_cols: {diag['numeric_cols']}")
    print(f"cat_cols: {diag['cat_cols']}")
    
    # Pipeline
    pipeline = run_base_compute_pipeline(file_bytes, "test_acp_numeric_id.csv")
    df = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    cat_cols = pipeline["cat_cols"]
    id_cols = pipeline["diagnosis"].get("id_cols", [])
    normality = pipeline["normality"]
    
    print(f"\n=== PIPELINE ===")
    print(f"numeric_cols (pipeline): {numeric_cols}")
    print(f"cat_cols (pipeline): {cat_cols}")
    print(f"id_cols (pipeline): {id_cols}")
    
    # Intent corrélation pour déclencher delegate_to_correlation
    intent = AnalysisIntent(
        action="correlation",
        target_col="SUP_HA",
        group_col="Rendement",
        predictor_cols=[],
        paired=False,
        raw_query="[auto]"
    )
    
    # Selector
    selector_output = select_and_run_test(
        intent, df, numeric_cols, cat_cols, id_cols, normality
    )
    
    print(f"\n=== SELECTOR OUTPUT ===")
    print(f"status: {selector_output.get('result', {}).get('status')}")
    
    # Résolution délégation (où l'ACP est ajoutée)
    fused_audit_log = []
    final_result = _resolve_delegation(
        selector_output, df, numeric_cols, normality,
        pipeline["regression"], pipeline["correlation"],
        fused_audit_log
    )
    
    print(f"\n=== RÉSULTAT FINAL ===")
    if "acp" in final_result:
        acp_result = final_result["acp"]
        print(f"ACP détecté dans le résultat")
        print(f"Variables ACP: {acp_result.get('variables', [])}")
        print(f"n_variables: {acp_result.get('n_variables')}")
        print(f"n_components: {acp_result.get('n_components')}")
        
        # Vérifier que ID n'est PAS dans les variables ACP
        if "ID" in acp_result.get("variables", []):
            print("✗ ERREUR: ID apparaît dans les variables ACP")
        else:
            print("✓ OK: ID n'apparaît PAS dans les variables ACP")
    else:
        print("ACP NON détecté dans le résultat")
    
    # Vérifier que les variables attendues sont présentes
    expected_vars = ["SUP_HA", "Rendement", "Production"]
    if "acp" in final_result:
        acp_vars = final_result["acp"].get("variables", [])
        missing = [v for v in expected_vars if v not in acp_vars]
        if missing:
            print(f"✗ ERREUR: Variables attendues manquantes: {missing}")
        else:
            print(f"✓ OK: Toutes les variables attendues sont présentes: {expected_vars}")
    
    print(f"\n=== AUDIT LOG ===")
    for entry in fused_audit_log:
        print(f"{entry['etape']}: {entry['decision']}")

if __name__ == "__main__":
    test_acp_with_numeric_id()
