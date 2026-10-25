"""Dataset import tracking endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.dataset_import import DatasetImport
from app.schemas.dataset_import import DatasetImportRead

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get(
    "/{import_id}",
    response_model=DatasetImportRead,
    summary="Get import status",
    description="Returns summary and audit counts for a specific dataset import job.",
)
async def get_import(
    import_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> DatasetImportRead:
    result = await db.execute(select(DatasetImport).where(DatasetImport.import_id == import_id))
    db_import = result.scalar_one_or_none()
    if not db_import:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import record not found: {import_id}",
        )
    return DatasetImportRead.model_validate(db_import)
