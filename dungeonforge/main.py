import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dungeonforge.api.routes import router
from dungeonforge.api.library_routes import router as library_router
from dungeonforge.api.weg_routes import router as weg_router
from dungeonforge.api.weg_vehicle_routes import router as weg_vehicle_router
from dungeonforge.api.weg_force_routes import router as weg_force_router
from dungeonforge.api.weg_advancement_routes import router as weg_advancement_router
from dungeonforge.api.weg_dark_routes import router as weg_dark_router
from dungeonforge.api.weg_creation_routes import router as weg_creation_router
from dungeonforge.api.weg_droid_routes import router as weg_droid_router
from dungeonforge.api.weg_engineering_routes import router as weg_engineering_router
from dungeonforge.api.weg_navigation_routes import router as weg_navigation_router
from dungeonforge.api.weg_hazard_routes import router as weg_hazard_router
from dungeonforge.api.weg_task_routes import router as weg_task_router
from dungeonforge.api.strahd_routes import router as strahd_router
from dungeonforge.api.weg_equipment_routes import router as weg_equipment_router
from dungeonforge.api.weg_template_routes import router as weg_template_router
from dungeonforge.api.weg_tactics_routes import router as weg_tactics_router
from dungeonforge.api.weg_medical_routes import router as weg_medical_router
from dungeonforge.api.weg_explosives_routes import router as weg_explosives_router
from dungeonforge.api.weg_favor_routes import router as weg_favor_router
from dungeonforge.api.weg_gear_effect_routes import router as weg_gear_effect_router

app = FastAPI(title="DungeonForge AI RPG Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(library_router)
app.include_router(weg_router)
app.include_router(weg_vehicle_router)
app.include_router(weg_force_router)
app.include_router(weg_advancement_router)
app.include_router(weg_dark_router)
app.include_router(weg_creation_router)
app.include_router(weg_droid_router)
app.include_router(weg_engineering_router)
app.include_router(weg_navigation_router)
app.include_router(weg_hazard_router)
app.include_router(weg_task_router)
app.include_router(strahd_router)
app.include_router(weg_equipment_router)
app.include_router(weg_template_router)
app.include_router(weg_tactics_router)
app.include_router(weg_medical_router)
app.include_router(weg_explosives_router)
app.include_router(weg_favor_router)
app.include_router(weg_gear_effect_router)

# Mount static assets (campaign images, portraits, maps)
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount frontend build static files if present
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dungeonforge.main:app", host="127.0.0.1", port=8000, reload=True)
