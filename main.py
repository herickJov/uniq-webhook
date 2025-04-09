
# main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging
import requests
from datetime import datetime

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook")

BITRIX_WEBHOOK_URL = "https://b24-rwd8iz.bitrix24.com.br/rest/94/as72rxtjh98pszj4/crm.lead.add"

@app.get("/")
def root():
    return {"status": "ok", "message": "Root route."}

@app.get("/webhook")
def get_webhook():
    return {"status": "ok", "message": "GET method not allowed for webhook."}

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        headers = dict(request.headers)
        body = await request.json()
        logger.info("===== NOVA REQUISIÇÃO RECEBIDA =====")
        logger.info("Headers: %s", headers)
        logger.info("Body: %s", body)

        if body.get("type") == "CALL":
            payload = body.get("payload", {})
            caller = payload.get("caller", "")
            called = payload.get("called", "")

            # Criação do lead no Bitrix24
            bitrix_payload = {
                "fields": {
                    "TITLE": f"Ligação recebida via Uniq - {datetime.utcnow().isoformat()}",
                    "NAME": "Cliente Uniq",
                    "LAST_NAME": "Recebido",
                    "PHONE": [{"VALUE": str(called), "VALUE_TYPE": "WORK"}],
                    "STATUS_ID": "NEW"
                }
            }

            bitrix_response = requests.post(BITRIX_WEBHOOK_URL, json=bitrix_payload)
            logger.info("Resposta Bitrix24: %s", bitrix_response.json())

        return JSONResponse(content={"received": True, "data": body}, status_code=200)

    except Exception as e:
        logger.exception("Erro ao processar webhook: %s", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
