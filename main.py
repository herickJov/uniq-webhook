# Patch status only in description logic

from fastapi import FastAPI, Request
import requests
import logging
from datetime import datetime

app = FastAPI()
logging.basicConfig(level=logging.INFO)

BITRIX_WEBHOOK_BASE = "https://b24-rwd8iz.bitrix24.com.br/rest/94/as72rxtjh98pszj4"

UNIQ_TO_BITRIX = {
    "1529": 36,
    "1557": 38,
    "1560": 34,
    "1520": 30,
    "1810": 94
}

UNIQ_TO_DDD = {
    "1529": "11",
    "1557": "11",
    "1560": "71",
    "1520": "71",
    "1810": "11"
}

seen_payload_ids = set()

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
    times = payload.get("times", {})
    payload_id = payload.get("id")
    duration = payload.get("duration", 0)

    if not payload_id:
        return {"status": "missing-id"}
    if payload_id in seen_payload_ids:
        logging.warning(f"Chamada duplicada ignorada: {payload_id}")
        return {"status": "duplicate"}

    seen_payload_ids.add(payload_id)

    if not subscribers:
        return {"status": "invalid-payload"}

    colaborador_info = next((sub for sub in subscribers if sub.get("type") == "user"), None)
    if not colaborador_info:
        logging.warning("Nenhum colaborador com type 'user' encontrado")
        return {"status": "user-not-found"}

    colaborador = colaborador_info.get("display", "Desconhecido")
    ramal = colaborador_info.get("number", "")
    bitrix_user_id = UNIQ_TO_BITRIX.get(ramal)

    if not bitrix_user_id:
        logging.warning(f"Ramal {ramal} não mapeado para usuário Bitrix")
        return {"status": "user-not-mapped"}

    remote_info = next((sub for sub in subscribers if sub.get("type") == "remote"), None)
    if not remote_info:
        logging.warning("Nenhum subscriber remoto encontrado")
        return {"status": "remote-not-found"}

    remote_number = remote_info.get("number", "")
    if not remote_number:
        logging.warning("Número remoto não encontrado")
        return {"status": "remote-number-not-found"}

    numero = normalize_phone(remote_number, ramal)
    logging.info(f"Número normalizado (destino - remoto): {numero}")

    try:
        setup_ts = times.get("setup", 0)
        setup_ts_adjusted = setup_ts + 10800

        telephony_payload = {
            "USER_ID": bitrix_user_id,
            "PHONE_NUMBER": numero,
            "CALL_START_DATE": datetime.fromtimestamp(setup_ts_adjusted).isoformat(),
            "CALL_DURATION": int(duration),
            "CALL_ID": payload_id,
            "TYPE": 1,
        }
        tel_resp = requests.post(
            f"{BITRIX_WEBHOOK_BASE}/telephony.externalcall.register.json",
            json=telephony_payload
        )
        tel_result = tel_resp.json()
        logging.info(f"Registro na telefonia: {tel_result}")

        if not tel_result.get("result"):
            return {"status": "telephony-register-failed"}

        bitrix_call_id = tel_result["result"]["CALL_ID"]

        finish_payload = {
            "CALL_ID": bitrix_call_id,
            "USER_ID": bitrix_user_id,
            "DURATION": int(duration),
            "STATUS_CODE": 200,
            "RECORD_URL": f"https://admin.uniq.app/recordings/details/{payload_id}",
            "ADD_TO_CHAT": 0
        }
        requests.post(
            f"{BITRIX_WEBHOOK_BASE}/telephony.externalcall.finish.json",
            json=finish_payload
        )

        contatos_res = requests.get(
            f"{BITRIX_WEBHOOK_BASE}/crm.contact.list.json",
            params={"filter[PHONE]": numero, "select[]": ["ID", "NAME"]}
        )
        contatos = contatos_res.json().get("result", [])
        if not contatos:
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
            return {"status": "no-deal"}

        start_ts = times.get("setup", 0)
        end_ts = times.get("release", 0)
        start = datetime.fromtimestamp(start_ts).isoformat()
        end = datetime.fromtimestamp(end_ts).isoformat()
        duracao_segundos = int(duration)
        duracao_minutos = duracao_segundos // 60
        duracao_display = f"{duracao_minutos} minutos" if duracao_segundos >= 60 else f"{duracao_segundos} segundos"

        gravacao_url = f"https://admin.uniq.app/recordings/details/{payload_id}"

        if duracao_segundos == 0:
            status_custom = "Incompleta"
        elif 1 <= duracao_segundos <= 4:
            status_custom = "Caixa postal"
        else:
            status_custom = "Efetuada"

        descricao = (
            f"Ligação registrada automaticamente via Uniq<br>"
            f"Contato: {contato_nome}<br>"
            f"Negócio: {negocio_titulo}<br>"
            f"Atendente: {colaborador}<br>"
            f"Duração: {duracao_display}<br>"
            f"Gravação: {gravacao_url}<br>"
            f"<br>Status: {status_custom}"
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
        return {"status": "ok"}

    except Exception as e:
        logging.error(f"Erro: {e}")
        return {"status": "error", "detail": str(e)}
