from fastapi import FastAPI

from app.api import routes_topup, routes_webhook

app = FastAPI(title="Virtual Top-Up API", version="0.1.0")

app.include_router(routes_topup.router)
app.include_router(routes_webhook.router)


@app.get("/health")
def health():
    return {"status": "ok"}
