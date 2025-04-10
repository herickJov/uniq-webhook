import os
import logging
import requests
from datetime import datetime
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

BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL")

UNIQ_TO_BITRIX_USER_IDS = {
    "1529": 36,
    "1557": 38,
    "1560": 34,
    "1520": 30,
    "1810": 94,
}

def normalize_phone(phone):
    if phone.startswith("0"):
        return phone[1:]
    return phone

def find_deal_by_phone_and_responsible(phone, responsible_id):
    url = f"{BITRIX_WEBHOOK_URL}/crm.deal.list"
    params = {
        "filter[TYPE_ID]": "SALE",
        "filter[STAGE_SEMANTIC_ID]": "P",
        "filter[ASSIGNED_BY_ID]": responsible_id,
        "filter[%CONTACT.PHONE]": phone,
        "select[]": "ID"
    }
    response = requests.get(url, params=params)
    deals = response.json().get("result", [])
    if deals:
        return deals[0]["ID"]
    return None

def log_call_to_bitrix(data):
    try:
        sessions = data["payload"].get("sessions", [])
        subscribers = data["payload"].get("subscribers", [])
        segments = data["payload"].get("segments", [])

        caller_session = next((s for s in sessions if s["direction"] == "INGRESS"), {})
        callee_session = next((s for s in sessions if s["direction"] == "EGRESS"), {})
        caller_subscriber_id = caller_session.get("subscriber", "")
        callee_subscriber_id = callee_session.get("subscriber", "")

        caller_number = next((s["number"] for s in subscribers if s["id"] == caller_subscriber_id), "")
        callee_number = next((s["number"] for s in subscribers if s["id"] == callee_subscriber_id), "")
        caller_name = next((s["display"] for s in subscribers if s["id"] == caller_subscriber_id), "")

        uniq_id = caller_number
        responsible_id = UNIQ_TO_BITRIX_USER_IDS.get(uniq_id)
        if not responsible_id:
            logging.warning(f"Responsável não encontrado para uniq_id {uniq_id}")
            return

        normalized_number = normalize_phone(callee_number)
        deal_id = find_deal_by_phone_and_responsible(normalized_number, responsible_id)
        if not deal_id:
            logging.warning(f"Nenhum negócio encontrado para {normalized_number} com responsável {responsible_id}")
            return

        start = datetime.utcfromtimestamp(data["payload"]["time_start"])
        end = datetime.utcfromtimestamp(data["payload"]["times"]["release"])

        call_data = {
            "fields": {
                "OWNER_ID": deal_id,
                "OWNER_TYPE_ID": 2,
                "TYPE_ID": 2,
                "DIRECTION": 2,
                "SUBJECT": f"Chamada de {caller_name} para {callee_number}",
                "COMPLETED": "Y",
                "DESCRIPTION": f"Ligação realizada por {caller_name} via Uniq",
                "DESCRIPTION_TYPE": 1,
                "COMMUNICATIONS": [
                    {
                        "VALUE": callee_number,
                        "TYPE": "PHONE"
                    }
                ],
                "START_TIME": start.isoformat(),
                "END_TIME": end.isoformat(),
                "RESPONSIBLE_ID": responsible_id
            }
        }

        requests.post(f"{BITRIX_WEBHOOK_URL}/crm.activity.add", json=call_data)
        logging.info("Registro adicionado no negócio com sucesso")

    except Exception as e:
        logging.error(f"Erro ao processar chamada: {e}")

@app.post("/uniq-calls")
async def receive_call(request: Request):
    body = await request.json()
    logging.info(f"Body: {body}")
    log_call_to_bitrix(body)
    return {"status": "received"}
