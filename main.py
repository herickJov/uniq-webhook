from fastapi import FastAPI, Request
import requests
import logging
from datetime import datetime

app = FastAPI()
logging.basicConfig(level=logging.INFO)

BITRIX_WEBHOOK_BASE = "https://b24-rwd8iz.bitrix24.com.br/rest/94/as72rxtjh98pszj4"

UNIQ_TO_BITRIX = {
    "1529": 36,  # SP, FABRICIO
    "1557": 38,  # SP, PRISCILA
    "1560": 34,  # BA, JOÃO
    "1520": 30,  # BA, NELMARA
    "1810": 94   # SP
}

UNIQ_TO_DDD = {
    "1529": "11",
    "1557": "11",
    "1560": "71",
    "1520": "71",
    "1810": "11"
}

def normalize_phone(phone, ramal):
    phone = ''.join(filter(str.isdigit, phone))
    if phone.startswith("0"):
        phone = phone[1:]
    if len(phone) in (8, 9) and ramal in UNIQ_TO_DDD:
        phone = UNIQ_TO_DDD[ramal] + phone
    if not phone.startswith("55"):
        phone = "55" + phone
    return f"+{phone}"

@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    logging.info(f"Payload recebido: {data}")

    payload = data.get("payload", {})
    subscribers = payload.get("subscribers", [])
    called = payload.get("called", "")
    times = payload.get("times", {})
    status = payload.get("status", "Desconhecido")
    payload_id = payload.get("id")

    if not subscribers or not called:
        return {"status": "invalid-payload"}

    colaborador = subscribers[0].get("display", "Desconhecido")
    ramal = subscribers[0].get("number", "")
    bitrix_user_id = UNIQ_TO_BITRIX.get(ramal)

    if not bitrix_user_id:
        logging.warning(f"Ramal {ramal} não mapeado para usuário Bitrix")
        return {"status": "user-not-mapped"}

    numero = normalize_phone(called, ramal)
    logging.info(f"Número normalizado: {numero}")

    try:
        contatos_res = requests.get(
            f"{BITRIX_WEBHOOK_BASE}/crm.contact.list.json",
            params={"filter[PHONE]": numero, "select[]": ["ID", "NAME"]}
        )
        contatos = contatos_res.json().get("result", [])
        if not contatos:
            logging.warning(f"Nenhum contato encontrado para o número {numero}")
            return {"status": "no-contact"}

        contato_id = int(contatos[0]['ID'])
        contato_nome = contatos[0]['NAME']

        negocios_res = requests.get(
            f"{BITRIX_WEBHOOK_BASE}/crm.deal.list.json",
            params={
                "filter[CONTACT_ID]": contato_id,
                "filter[ASSIGNED_BY_ID]": bitrix_user_id,
                "filter[STAGE_SEMANTIC_ID]": "P",
                "select[]": ["ID", "TITLE", "ASSIGNED_BY_ID"]
            }
        )
        negocios = negocios_res.json().get("result", [])

        negocio_id = None
        negocio_titulo = ""
        for deal in negocios:
            if str(deal.get("ASSIGNED_BY_ID")) == str(bitrix_user_id):
                negocio_id = int(deal['ID'])
                negocio_titulo = deal['TITLE']
                break

        if not negocio_id:
            logging.warning(f"Nenhum negócio encontrado para contato {numero} com responsável {bitrix_user_id}")
            return {"status": "no-deal"}

        start_ts = times.get("setup", 0)
        end_ts = times.get("release", 0)
        start = datetime.fromtimestamp(start_ts).isoformat()
        end = datetime.fromtimestamp(end_ts).isoformat()
        duracao = int(end_ts - start_ts) if end_ts > start_ts else 0

        gravacao_url = f"https://admin.uniq.app/recordings/details/{payload_id}"

        descricao = (
            f"Ligação registrada automaticamente via Uniq<br>"
            f"Contato: {contato_nome}<br>"
            f"Negócio: {negocio_titulo}<br>"
            f"Atendente: {colaborador}<br>"
            f"Duração: {duracao} segundos<br>"
            f"Status: {status}<br>"
            f"Gravação: {gravacao_url}"
        )

        activity_payload = {
            "fields": {
                "OWNER_ID": negocio_id,
                "OWNER_TYPE_ID": 2,
                "TYPE_ID": 2,
                "SUBJECT": f"Ligação via Uniq de {colaborador} para {numero}",
                "COMMUNICATIONS": [
                    {
                        "VALUE": numero,
                        "TYPE": "PHONE",
                        "ENTITY_TYPE_ID": 3,
                        "ENTITY_ID": contato_id
                    }
                ],
                "BINDINGS": [
                    {
                        "OWNER_ID": negocio_id,
                        "OWNER_TYPE_ID": 2
                    }
                ],
                "RESPONSIBLE_ID": bitrix_user_id,
                "DESCRIPTION": descricao,
                "DESCRIPTION_TYPE": 3,
                "START_TIME": start,
                "END_TIME": end,
                "COMPLETED": "Y",
                "DIRECTION": 2
            }
        }

        activity_res = requests.post(
            f"{BITRIX_WEBHOOK_BASE}/crm.activity.add.json",
            json=activity_payload
        )

        logging.info(f"Atividade registrada: {activity_res.json()}")
        logging.info(f"Contato: {contato_nome} | ID: {contato_id} | Responsável: {bitrix_user_id}")
        logging.info(f"Negócio usado: {negocio_titulo} | ID: {negocio_id}")

        return {"status": "ok"}

    except Exception as e:
        logging.error(f"Erro: {e}")
        return {"status": "error", "detail": str(e)}
