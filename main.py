import json
import logging
import time
from datetime import datetime

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)

BITRIX_WEBHOOK_URL = "https://b24-rwd8iz.bitrix24.com.br/rest/94/as72rxtjh98pszj4"


def buscar_negocio_por_telefone(telefone: str):
    telefone = telefone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    search_payload = {
        "type": "PHONE",
        "values": [telefone]
    }

    try:
        r = requests.post(BITRIX_WEBHOOK_URL + "/crm.duplicate.findbycomm", json=search_payload)
        r.raise_for_status()
        data = r.json()

        entity_id = None
        if data.get("result"):
            if data["result"].get("CONTACT"):
                entity_id = data["result"]["CONTACT"][0]
                owner_type = "C"
            elif data["result"].get("LEAD"):
                entity_id = data["result"]["LEAD"][0]
                owner_type = "L"
            else:
                return None

            deal_filter = {
                "filter": {
                    f"{owner_type}ID": entity_id
                },
                "select": ["ID"],
                "order": {"ID": "DESC"},
                "start": 0
            }
            r = requests.post(BITRIX_WEBHOOK_URL + "/crm.deal.list", json=deal_filter)
            r.raise_for_status()
            deals = r.json().get("result", [])
            if deals:
                return int(deals[0]["ID"])
    except Exception as e:
        logging.error("Erro ao buscar negócio: %s", e)

    return None


def registrar_atividade_chamada(called, colaborador, start_ts, end_ts):
    negocio_id = buscar_negocio_por_telefone(called)

    if not negocio_id:
        logging.warning("Nenhum negócio encontrado para o número %s", called)
        return {"status": "no-deal-found"}

    start_time_str = datetime.fromtimestamp(start_ts).isoformat()
    end_time_str = datetime.fromtimestamp(end_ts).isoformat()

    activity_payload = {
        "fields": {
            "OWNER_ID": negocio_id,
            "OWNER_TYPE_ID": 2,  # Deal
            "TYPE_ID": 2,        # Call
            "DIRECTION": 2,      # Outgoing
            "SUBJECT": f"Chamada de {colaborador} para {called}",
            "COMPLETED": "Y",
            "DESCRIPTION": f"Ligação realizada por {colaborador} via Uniq",
            "DESCRIPTION_TYPE": 1,
            "COMMUNICATIONS": [{"VALUE": called, "TYPE": "PHONE"}],
            "START_TIME": start_time_str,
            "END_TIME": end_time_str
        }
    }

    try:
        logging.info("Enviando para Bitrix: %s", json.dumps(activity_payload, indent=2))
        res = requests.post(BITRIX_WEBHOOK_URL + "/crm.activity.add", json=activity_payload)
        res.raise_for_status()
        logging.info("Resposta Bitrix24: %s", res.json())
        return res.json()
    except Exception as e:
        logging.error("Erro ao enviar atividade para Bitrix: %s", e)
        return {"status": "bitrix-error", "error": str(e)}


@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.json()
    logging.info("===== NOVA REQUISIÇÃO RECEBIDA =====")
    logging.info("Body: %s", body)

    if body.get("type") == "CALL":
        payload = body.get("payload", {})
        called = payload.get("called")
        start = payload.get("times", {}).get("setup", time.time())
        end = payload.get("times", {}).get("release", time.time())
        subscribers = payload.get("subscribers", [])
        colaborador = subscribers[0].get("display") if subscribers else "Desconhecido"

        resultado = registrar_atividade_chamada(
            called=called,
            colaborador=colaborador,
            start_ts=start,
            end_ts=end
        )
        return resultado

    return {"status": "ignored"}
