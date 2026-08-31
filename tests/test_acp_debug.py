"""Debug pour comprendre pourquoi l'ACP n'est pas déclenchée sur test_acp_numeric_id.csv."""
from app.compute.upload_validation import load_and_diagnose
from app.compute.compute import run_base_compute_pipeline, run_acp

def debug_acp():
    """Debug run_acp directement."""
    print("=== DEBUG: run_acp direct sur test_acp_numeric_id.csv ===")
    
    with open("tests/test_acp_numeric_id.csv", "rb") as f:
        file_bytes = f.read()
    
    # Pipeline
    pipeline = run_base_compute_pipeline(file_bytes, "test_acp_numeric_id.csv")
    df = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    
    print(f"numeric_cols: {numeric_cols}")
    print(f"len(numeric_cols): {len(numeric_cols)}")
    print(f"df shape: {df.shape}")
    print(f"df columns: {df.columns.tolist()}")
    
    # Appel direct à run_acp
    print(f"\n=== APPEL DIRECT À run_acp ===")
    acp_result = run_acp(df, numeric_cols)
    
    print(f"status: {acp_result.get('status')}")
    if acp_result.get("status") == "error":
        print(f"error: {acp_result.get('error')}")
    else:
        print(f"n_variables: {acp_result.get('n_variables')}")
        print(f"variables: {acp_result.get('variables')}")

if __name__ == "__main__":
    debug_acp()
