import sys

sys.path.insert(0, r"C:\Users\23eg1\OneDrive\Documents\n8n\backend_vendor")

import uvicorn

uvicorn.run("app.main:app", host="127.0.0.1", port=8001)
