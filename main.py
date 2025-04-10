import logging
import requests
from fastapi import FastAPI, Request
from datetime import datetime
from pytz import timezone

app = FastAPI()
logging.basicConfig(level=logging.INFO)

BITRIX_WEBHOOK = "https://SEUDOMINIO.bitrix24.com/rest/ID/CHAVE/"
BITRIX_TIMEZONE = timezone("America/Sao_Paulo")

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logging.info(f"Payload recebido: {data}")

    call_number = data.get("caller_id_number")
    call_type = data.get("direction")  # inbound ou outbound

    if not call_number:
        return {"error": "Número não encontrado no payload."}

    response = requests.post(BITRIX_WEBHOOK + "crm.deal.list.json", json={
        "filter": {"PHONE": call_number},
        "select": ["ID", "TITLE"]
    })

    deals = response.json().get("result", [])
    if not deals:
        return {"error": "Nenhum negócio encontrado com esse número."}

    deal_id = deals[0]['ID']
    agora = datetime.now(BITRIX_TIMEZONE)
    
    resultado = requests.post(BITRIX_WEBHOOK + "crm.activity.add.json", json={
        "fields": {
            "OWNER_ID": deal_id,
            "OWNER_TYPE_ID": 2,  # 2 = Negócio
            "TYPE_ID": 2,  # 2 = Chamada telefônica
            "SUBJECT": f"Ligação {call_type} recebida via Uniq - {agora.strftime('%Y-%m-%d %H:%M:%S')}",
            "START_TIME": agora.isoformat(),
            "END_TIME": agora.isoformat(),
            "COMPLETED": "Y",
            "COMMUNICATIONS": [
                {"VALUE": call_number, "TYPE": "PHONE"}
            ]
        }
    })

    logging.info(f"Atividade registrada: {resultado.json()}")
    return resultado.json()
