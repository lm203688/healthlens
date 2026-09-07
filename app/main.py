import uvicorn
from app import get_app

# Expose app for uvicorn and Docker CMD
app = get_app()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
