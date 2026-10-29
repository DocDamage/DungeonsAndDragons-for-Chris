from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from dungeonforge.library import FOLDERS, get_library


router = APIRouter(prefix="/api/library", tags=["Local library"])


@router.get("")
def catalog():
    return get_library().catalog()


@router.post("/index")
def index_library(folder_id: str | None = None):
    try:
        return {"job": get_library().start_index(folder_id)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/search")
def search_library(q: str, folder_id: str | None = None, edition: str | None = None, limit: int = Query(8, ge=1, le=30)):
    if folder_id is not None and folder_id not in FOLDERS:
        raise HTTPException(status_code=422, detail="Unknown library folder.")
    return {"results": get_library().search(q, folder_id=folder_id, edition=edition, limit=limit)}


@router.get("/sources/{source_id}/file")
def source_file(source_id: str):
    path = get_library().source_file(source_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Source file not found.")
    return FileResponse(path, filename=path.name, content_disposition_type="inline")
