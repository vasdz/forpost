from fastapi import FastAPI

from forpost_api.routes.v1.risks import router as risks_router

app = FastAPI(
    title="Форпост API",
    description="Платформа прогнозирования рисков инженерной инфраструктуры",
    version="0.1.0",
)

app.include_router(risks_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "system": "forpost"}
