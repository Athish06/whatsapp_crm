"""
WhatsApp CRM API Server
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv
import logging

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Import config after loading env
from config import Database, settings

# Create FastAPI app
app = FastAPI(title="WhatsApp CRM API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from routes import auth, customers, templates, batches, dashboard, files

app.include_router(auth.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(batches.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(files.router, prefix="/api")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup."""
    try:
        # Verify database connection
        db = Database.get_database()
        await db.command("ping")
        logger.info("Connected to MongoDB successfully")
    except Exception as e:
        logger.warning(f"Could not connect to MongoDB: {e}")
        logger.warning("App starting without database connection. Ensure MongoDB is running.")


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connection on shutdown."""
    await Database.close()
    logger.info("Disconnected from MongoDB")


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
