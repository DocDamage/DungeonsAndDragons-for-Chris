import sys
import os

# Ensure package is on python path
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("dungeonforge.main:app", host="127.0.0.1", port=8000, reload=True)
