from fastapi import FastAPI


logger = logger.getLogging(__name__)

app = FastAPI()

@app.get("/health")
async def get_health():
    return {
        "status" : "healthy"
    }
