from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

app = FastAPI()
logging.basicConfig(level=logging.INFO)

@app.post("/webhook")
async def uniq_webhook_listener(request: Request):
    try:
        payload = await request.json()
        logging.info("📨 Evento recebido do Uniq:")
        logging.info(payload)
        return JSONResponse(content={"status": "ok"}, status_code=200)
    except Exception as e:
        logging.error(f"❌ Erro ao processar webhook: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=400)
