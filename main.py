import json
import uvicorn
from fastapi import FastAPI, Request
import httpx
import logging

logging.basicConfig(level=logging.INFO)
app = FastAPI()

BITRIX_WEBHOOK = "https://seusubdominio.bitrix24.com/rest/1/chavewebhook/"
HEADERS = {"Content-Type": "application/json"}

OWNER_TYPE_ID_DEAL = 2
ACTIVITY_TYPE_CALL = 2

@app.post("/webhook")
async def handle_webhook(request: Request):
    payload = await request.json()
    logging.info("Payload recebido: %s", payload)

    phone_number = payload.get("caller_id")
    call_start = payload.get("start")
    colaborador = payload.get("agent_name", "Desconhecido")
    user_id = payload.get("user_id")

    if not phone_number:
        return {"error": "caller_id ausente"}

    # 1. Buscar contatos com esse telefone
    async with httpx.AsyncClient() as client:
        contact_search_response = await client.post(
            BITRIX_WEBHOOK + "crm.contact.list",
            headers=HEADERS,
            json={
                "filter": {"PHONE": phone_number},
                "select": ["ID", "NAME"]
            }
        )

    contacts = contact_search_response.json().get("result", [])

    if not contacts:
        logging.warning("Nenhum contato encontrado para o número: %s", phone_number)
        return {"message": "Sem contato correspondente"}

    contact_id = contacts[0]["ID"]

    # 2. Buscar negócios vinculados ao contato e usuário
    async with httpx.AsyncClient() as client:
        deal_search_response = await client.post(
            BITRIX_WEBHOOK + "crm.deal.list",
            headers=HEADERS,
            json={
                "filter": {
                    "CONTACT_ID": contact_id,
                    "ASSIGNED_BY_ID": user_id,
                    "STAGE_SEMANTIC_ID": "P"
                },
                "select": ["ID", "TITLE"]
            }
        )

    deals = deal_search_response.json().get("result", [])

    if not deals:
        logging.warning("Nenhum negócio encontrado para o número: %s e responsável: %s", phone_number, user_id)
        return {"message": "Sem negócio correspondente para esse responsável"}

    deal_id = deals[0]["ID"]
    logging.info("Negócio encontrado: %s", deal_id)

    # 3. Criar atividade ligada ao negócio
    atividade_payload = {
        "fields": {
            "OWNER_ID": deal_id,
            "OWNER_TYPE_ID": OWNER_TYPE_ID_DEAL,
            "TYPE_ID": ACTIVITY_TYPE_CALL,
            "SUBJECT": f"Ligação recebida via Uniq de {colaborador} - {call_start}",
            "DESCRIPTION": f"Ligação recebida de {phone_number} por {colaborador}",
            "DESCRIPTION_TYPE": 1,
            "DIRECTION": 1,
            "RESPONSIBLE_ID": user_id,
            "COMPLETED": "Y",
            "COMMUNICATIONS": [
                {
                    "VALUE": phone_number,
                    "TYPE": "PHONE"
                }
            ]
        }
    }

    async with httpx.AsyncClient() as client:
        activity_response = await client.post(
            BITRIX_WEBHOOK + "crm.activity.add",
            headers=HEADERS,
            json=atividade_payload
        )

    result = activity_response.json()
    logging.info("Atividade registrada: %s", result)
    return result

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
