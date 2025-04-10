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

def normalizar_telefone(telefone: str) -> str:
    numero = telefone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if numero.startswith("0") and len(numero) >= 11:
        numero = numero[1:]
    return numero

def buscar_lead_ou_contato_por_telefone(telefone: str):
    telefone = normalizar_telefone(telefone)

    search_payload = {
        "type": "PHONE",
        "values": [telefone]
    }

    try:
        r = requests.post(BITRIX_WEBHOOK_URL + "/crm.duplicate.findbycomm", json=search_payload)
        r.raise_for_status()
        data = r.json()

        if data.get("result"):
            contatos = data["result"].get("CONTACT", [])
            for contato_id in contatos:
                res = requests.post(BITRIX_WEBHOOK_URL + "/crm.contact.get", json={"id": contato_id})
                res.raise_for_status()
                contato = res.json().get("result", {})
                for fone in contato.get("PHONE", []):
                    if normalizar_telefone(fone.get("VALUE", "")) == telefone:
                        return {"type_id": 3, "id": contato_id}  # CONTACT

            leads = data["result"].get("LEAD", [])
            for lead_id in leads:
                res = requests.post(BITRIX_WEBHOOK_URL + "/crm.lead.get", json={"id": lead_id})
                res.raise_for_status()
                lead = res.json().get("result", {})
                for fone in lead.get("PHONE", []):
                    if normalizar_telefone(fone.get("VALUE", "")) == telefone:
                        return {"type_id": 1, "id": lead_id}  # LEAD

    except Exception as e:
        logging.error("Erro ao buscar lead/contato exato: %s", e)

    return None

def registrar_atividade_chamada(called, colaborador, start_ts, end_ts):
    entidade = buscar_lead_ou_contato_por_telefone(called)

    if not entidade:
        logging.warning("Nenhum lead ou contato exato encontrado para o número %s", called)
        return {"status": "no-entity-found"}

    start_time_str = datetime.fromtimestamp(start_ts).isoformat()
    end_time_str = datetime.fromtimestamp(end_ts).isoformat()
    telefone_normalizado = normalizar_telefone(called)

    activity_payload = {
        "fields": {
            "OWNER_ID": entidade["id"],
            "OWNER_TYPE_ID": entidade["type_id"],
            "TYPE_ID": 2,
            "DIRECTION": 2,
            "SUBJECT": f"Chamada de {colaborador} para {telefone_normalizado}",
            "COMPLETED": "Y",
            "DESCRIPTION": f"Ligação realizada por {colaborador} via Uniq",
            "DESCRIPTION_TYPE": 1,
            "COMMUNICATIONS": [{"VALUE": telefone_normalizado, "TYPE": "PHONE"}],
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
