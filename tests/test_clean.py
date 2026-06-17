"""Test pipeline sur dataset propre (sans NA, sans outliers marqués)."""
from tests._print_pipeline import run_sample

if __name__ == "__main__":
    run_sample("clean.csv")
