"""Run Phase 2 generation evaluation from the project root.

PowerShell:
    python -m evaluation.run_generation_evaluation
"""

import logging

from evaluation.generation_evaluation_dataset import EVALUATION_DATASET
from evaluation.generation_evaluator import run_generation_evaluation


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    run_generation_evaluation(EVALUATION_DATASET)


if __name__ == "__main__":
    main()
