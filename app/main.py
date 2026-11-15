"""
Santa's Draw - Secret Santa API
Main application file
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time
import logging
from pathlib import Path
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.core.admin_auth import AdminGuardMiddleware, AdminLoginRequired
from app.models import init_db

logger = logging.getLogger(__name__)

# Initialize Sentry (Optional)
if settings.sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=1.0,
            integrations=[
                StarletteIntegration(transaction_style="url"),
                FastApiIntegration(transaction_style="url"),
                CeleryIntegration(),
                SqlalchemyIntegration(),
            ],
        )
        logger.info("✅ Sentry initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️  Sentry initialization failed: {e}")
else:
    logger.info("ℹ️  Sentry not configured (SENTRY_DSN not set)")

# API versioning from settings
API_VERSION = settings.api_version
API_PREFIX = f"/api/{API_VERSION}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown operations
    """
    # Startup
    print(f"🚀 Starting {settings.app_name}...")
    print(f"📌 API Version: {API_VERSION}")
    print(f"📌 API Prefix: {API_PREFIX}")
    print(f"🔧 Debug Mode: {settings.debug}")
    print(f"🗄️  Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'Not configured'}")
    
    # Initialize database
    try:
        init_db()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"⚠️  Database initialization failed: {e}")
    
    yield
    
    # Shutdown
    print(f"👋 Shutting down {settings.app_name}...")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="RESTful API for Secret Santa draw management",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    debug=settings.debug,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Added after CORS so it wraps it: admin responses must never carry CORS headers.
app.add_middleware(AdminGuardMiddleware)


@app.exception_handler(AdminLoginRequired)
async def admin_login_required(request, exc):
    return RedirectResponse("/admin/login", status_code=303)


@app.get("/", tags=["General"])
async def root():
    """
    Root endpoint - API information
    """
    return {
        "message": f"Welcome to {settings.app_name}! 🎄",
        "version": settings.app_version,
        "status": "running",
        "debug": settings.debug,
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", tags=["General"])
async def health_check():
    """
    Health check endpoint - Checks application status
    """
    # Check database connection
    db_status = "connected"
    try:
        from app.models.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"disconnected: {str(e)}"
    
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "uptime": "running",
        "api_version": API_VERSION,
        "service": "santas-draw-api",
        "debug": settings.debug,
        "database": db_status
    }


# Include routers
from app.api.v1 import auth, draw, participant, device, email
app.include_router(auth.router, prefix=f"{API_PREFIX}/auth", tags=["Authentication"])
app.include_router(draw.router, prefix=f"{API_PREFIX}", tags=["Draw"])
app.include_router(participant.router, prefix=f"{API_PREFIX}", tags=["Participant"])
app.include_router(device.router, prefix=f"{API_PREFIX}", tags=["Device"])
app.include_router(email.router, prefix=f"{API_PREFIX}", tags=["Email"])

# Admin panel (read-only, server-rendered). Static files first so the router cannot shadow them.
from app.api import admin
app.mount(
    "/admin/static",
    StaticFiles(directory=str(Path(__file__).parent / "static" / "admin")),
    name="admin-static",
)
app.include_router(admin.router, prefix="/admin")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
