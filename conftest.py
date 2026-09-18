# Hace que la raíz del proyecto esté en sys.path al ejecutar los tests,
# para poder hacer `import secure`, `import anonymizer`, etc.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
