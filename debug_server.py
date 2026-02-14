import sys
import os
import traceback

sys.path.append(os.getcwd())

print("Attempting to import web.server...")
try:
    import web.server
    print("Import successful!")
    print("Starting server manually...")
    import uvicorn
    uvicorn.run(web.server.app, host="0.0.0.0", port=5000)
except Exception:
    print("Huston, we have a problem:")
    traceback.print_exc()
