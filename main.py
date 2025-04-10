from fastapi import FastAPI, Request
import requests
import logging
from datetime import datetime

app = FastAPI()
logging.basicConfig(level=logging.INFO)

BITRIX_WEBHOOK_BASE = "https://b24-rwd8iz.bitrix24.com.br/rest/94/as72rxtjh98pszj4"

# Mapeamento de IDs Uniq -> Bitrix
UNIQ_TO_BITRIX = {
    "1529": 36,
    "1557": 38,
    "1560": 34,
    "1520": 30,
    "1810": 94
}

def normalize_phone(phone):
    return phone.lstrip("0")

@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    logging.info(f"Payload recebido: {data}")

    # Coleta dados
    payload = data.get("payload", {})
    subscribers = payload.get("subscribers", [])
    called = payload.get("called", "")
    times = payload.get("times", {})

    if not subscribers or not called:
        return {"status": "invalid-payload"}

    colaborador = subscribers[0].get("display", "Desconhecido")
    ramal = subscribers[0].get("number", "")
    bitrix_user_id = UNIQ_TO_BITRIX.get(ramal)

    if not bitrix_user_id:
        logging.warning(f"Ramal {ramal} não mapeado para usuário Bitrix")
        return {"status": "user-not-mapped"}

    numero = normalize_phone(called)

    try:
        # Busca contatos com esse telefone
        contatos_res = requests.get(
            f"{BITRIX_WEBHOOK_BASE}/crm.contact.list",
            params={"filter[PHONE]": numero, "select[]": "ID"}
        )
        contatos = contatos_res.json().get("result", [])
        if not contatos:
            logging.warning(f"Nenhum contato encontrado para o número {numero}")
            return {"status": "no-contact"}

        contato_id = contatos[0]['ID']

        # Busca negócios vinculados ao contato e ao responsável
        negocios_res = requests.get(
            f"{BITRIX_WEBHOOK_BASE}/crm.deal.list",
            params={
                "filter[CONTACT_ID]": contato_id,
                "filter[ASSIGNED_BY_ID]": bitrix_user_id,
                "filter[STAGE_SEMANTIC_ID]": "P",
                "select[]": "ID"
            }
        )
        negocios = negocios_res.json().get("result", [])

        if not negocios:
            logging.warning(f"Nenhum negócio encontrado para {numero} e responsável {bitrix_user_id}")
            return {"status": "no-deal"}

        negocio_id = negocios[0]['ID']

        start = datetime.fromtimestamp(times.get("setup", 0)).isoformat()
        end = datetime.fromtimestamp(times.get("release", 0)).isoformat()

        activity_payload = {
            "fields": {
                "TYPE_ID": 2,
                "SUBJECT": f"Ligação via Uniq de {colaborador} para {numero}",
                "COMMUNICATIONS": [{
                    "VALUE": numero,
                    "TYPE": "PHONE"
                }],
                "BINDINGS": [{
                    "OWNER_ID": negocio_id,
                    "OWNER_TYPE_ID": 2
                }],
                "RESPONSIBLE_ID": bitrix_user_id,
                "DESCRIPTION": f"Ligação registrada automaticamente via Uniq",
                "DESCRIPTION_TYPE": 3,
                "START_TIME": start,
                "END_TIME": end,
                "COMPLETED": "Y",
                "DIRECTION": 2
            }
        }

        activity_res = requests.post(
            f"{BITRIX_WEBHOOK_BASE}/crm.activity.add",
            json=activity_payload
        )
        logging.info(f"Atividade registrada: {activity_res.json()}")
        return {"status": "ok"}

    except Exception as e:
        logging.error(f"Erro: {e}")
        return {"status": "error", "detail": str(e)}
