from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes import auth
from app.core.db import get_db

app = FastAPI(title="Secure RFP Platform", version="0.1.0")
app.include_router(auth.router)


@app.get("/health")
def health(response: Response, db: Session = Depends(get_db)) -> dict:
    """Report whether the API is up and can reach the database."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "db": False}
    return {"status": "ok", "db": True}
