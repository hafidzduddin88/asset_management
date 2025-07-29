from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.middleware.session_auth import SessionAuthMiddleware
from app.routes import login
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Asset Management System")

# Add session auth middleware
app.add_middleware(SessionAuthMiddleware)

# Mount static files (CSS, JS, images, etc.)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include route modules
app.include_router(login.router)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Root endpoint (optional redirect)
@app.get("/")
async def root():
    return {"message": "Asset Management System"}

# Run with `python main.py` in local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
