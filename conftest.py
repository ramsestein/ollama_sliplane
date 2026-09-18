# Makes the project root available on sys.path when running the tests,
# so that `import secure`, `import anonymizer`, etc. work.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
