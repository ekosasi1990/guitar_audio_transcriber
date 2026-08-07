import os
import sys

# Make sure the src/ package is on the import path for the bundled executable.
base = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(base, 'src')
if src not in sys.path:
    sys.path.insert(0, src)

import uvicorn  # noqa: E402
from backend.api import app  # noqa: E402

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=8000, reload=False)
