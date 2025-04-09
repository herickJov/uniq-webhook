# main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging
import requests
from datetime import datetime

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook")

BITRIX_BASE_URL = "https://b24-rwd8iz.bitrix24.com.br/rest/94/as72rxtjh98pszj4"

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
            called = payload.get("called")  # número do cliente
            subscribers = payload.get("subscribers", [])
            collaborator = subscribers[0]["display"] if subscribers else "Desconhecido"

            # Busca lead pelo número chamado
            search_url = f"{BITRIX_BASE_URL}/crm.lead.list"
            search_payload = {
                "filter": {"PHONE": called},
                "select": ["ID", "TITLE"]
            }
            search_res = requests.post(search_url, json=search_payload)
            search_data = search_res.json()

            if search_data.get("result"):
                lead_id = search_data["result"][0]["ID"]

                # Cria atividade de chamada vinculada ao lead
                activity_url = f"{BITRIX_BASE_URL}/crm.activity.add"
                activity_payload = {
                    "fields": {
                        "OWNER_ID": lead_id,
                        "OWNER_TYPE_ID": 1,  # 1 = Lead
                        "TYPE_ID": 2,        # 2 = Call
                        "DIRECTION": 2,      # 2 = Outgoing
                        "SUBJECT": f"Chamada de {collaborator} para {called}",
                        "COMPLETED": "Y",
                        "DESCRIPTION": f"Ligação realizada por {collaborator} via Uniq",
                        "DESCRIPTION_TYPE": 1,
                        "COMMUNICATIONS": [{"VALUE": called, "TYPE": "PHONE"}],
                        "START_TIME": datetime.utcnow().isoformat()
                    }
                }
                activity_res = requests.post(activity_url, json=activity_payload)
                logger.info("Atividade registrada: %s", activity_res.json())
            else:
# main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging
import requests
from datetime import datetime

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook")

BITRIX_BASE_URL = "https://b24-rwd8iz.bitrix24.com.br/rest/94/as72rxtjh98pszj4"

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
            called = payload.get("called")  # número do cliente
            subscribers = payload.get("subscribers", [])
            collaborator = subscribers[0]["display"] if subscribers else "Desconhecido"

            # Busca lead pelo número chamado
            search_url = f"{BITRIX_BASE_URL}/crm.lead.list"
            search_payload = {
                "filter": {"PHONE": called},
                "select": ["ID", "TITLE"]
            }
            search_res = requests.post(search_url, json=search_payload)
            search_data = search_res.json()

            if search_data.get("result"):
                lead_id = search_data["result"][0]["ID"]

                # Cria atividade de chamada vinculada ao lead
                activity_url = f"{BITRIX_BASE_URL}/crm.activity.add"
                activity_payload = {
                    "fields": {
                        "OWNER_ID": lead_id,
                        "OWNER_TYPE_ID": 1,  # 1 = Lead
                        "TYPE_ID": 2,        # 2 = Call
                        "DIRECTION": 2,      # 2 = Outgoing
                        "SUBJECT": f"Chamada de {collaborator} para {called}",
                        "COMPLETED": "Y",
                        "DESCRIPTION": f"Ligação realizada por {collaborator} via Uniq",
                        "DESCRIPTION_TYPE": 1,
                        "COMMUNICATIONS": [{"VALUE": called, "TYPE": "PHONE"}],
                        "START_TIME": datetime.utcnow().isoformat()
                    }
                }
                activity_res = requests.post(activity_url, json=activity_payload)
                logger.info("Atividade registrada: %s", activity_res.json())
            else:
                logger.warning("Lead não encontrado para o número: %s", called)

        return JSONResponse(content={"received": True, "data": body}, status_code=200)

    except Exception as e:
        logger.exception("Erro ao processar webhook: %s", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=10000)


