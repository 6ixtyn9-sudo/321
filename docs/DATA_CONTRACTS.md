# Data Contracts

We enforce strict schemas using Pydantic models in `src/soccer_factory/schemas/`.

- **RawSnapshot**: Immutable raw fetch data.
- **Match**: Normalized canonical match definition.
- **Features**: Model inputs with strict bounds (e.g. probabilities 0-1, goals >= 0).
- **Prediction**: Model output, including confidence grade (A, B, C, X).
- **Result**: Post-match ground truth.
- **Grading**: Walk-forward evaluation output.
