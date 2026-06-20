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

# Global scheduler instance
message_scheduler = None

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from routes import auth, customers, templates, batches, dashboard, files
from routes import shops as shops_router

app.include_router(auth.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(batches.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(shops_router.router, prefix="/api")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.on_event("startup")
async def startup_event():
    """Initialize database connection and start scheduler on startup."""
    global message_scheduler
    
    try:
        # Verify database connection
        db = Database.get_database()
        await db.command("ping")
        logger.info("Connected to MongoDB successfully")
        
        # Initialize database indexes
        await Database.initialize_indexes()
        logger.info("Database indexes initialized")
        
        # Run one-time database migration (customer_behavior_map -> customer_insights)
        try:
            from services import migrate_behavior_to_insights
            migration_res = await migrate_behavior_to_insights(db)
            logger.info(f"Database behavior map migration status: {migration_res}")
        except Exception as migration_err:
            logger.error(f"Failed to run database migration: {migration_err}")
        
        # Initialize and start scheduler worker
        from services.scheduler_service import SchedulerWorker
        message_scheduler = SchedulerWorker(db)
        message_scheduler.start()
        logger.info("Scheduler worker started")
        
    except Exception as e:
        logger.warning(f"Could not connect to MongoDB: {e}")
        logger.warning("App starting without database connection. Ensure MongoDB is running.")


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connection and stop scheduler on shutdown."""
    global message_scheduler
    
    # Stop scheduler worker
    if message_scheduler:
        message_scheduler.stop()
        logger.info("Scheduler worker stopped")
    
    # Close database connection
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
