from fastapi import FastAPI, Request
import httpx
import logging

app = FastAPI()
logging.basicConfig(level=logging.INFO)

BITRIX_WEBHOOK_BASE = "https://b24-rwd8iz.bitrix24.com.br/rest/9/your_webhook_key"

# Mapeamento de IDs Uniq -> Bitrix
UNIQ_TO_BITRIX = {
    "1529": 36,
    "1557": 38,
    "1560": 34,
    "1520": 30,
    "1810": 94
}

@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    logging.info(f"Payload recebido: {data}")

    numero = data.get("numero") or ""
    ramal = str(data.get("ramal"))
    if not numero or ramal not in UNIQ_TO_BITRIX:
        logging.warning("Número ou ramal inválido.")
        return {"status": "ignored"}

    # Remove prefixo 0 se vier como 0319xxxxxxx
    if numero.startswith("0"):
        numero = numero[1:]

    responsavel_id = UNIQ_TO_BITRIX[ramal]

    # Busca contatos com esse número
    async with httpx.AsyncClient() as client:
        contatos_res = await client.get(f"{BITRIX_WEBHOOK_BASE}/crm.contact.list", params={
            "filter[PHONE]": numero
        })
        contatos = contatos_res.json().get("result", [])

        if not contatos:
            logging.warning(f"Nenhum contato encontrado para o número {numero}")
            return {"status": "no contact"}

        contato_id = contatos[0]['ID']

        # Buscar negócio (deal) aberto com esse contato e responsável
        negocios_res = await client.get(f"{BITRIX_WEBHOOK_BASE}/crm.deal.list", params={
            "filter[CONTACT_ID]": contato_id,
            "filter[STAGE_SEMANTIC_ID]": "P",  # Apenas negócios em andamento
            "filter[ASSIGNED_BY_ID]": responsavel_id
        })
        negocios = negocios_res.json().get("result", [])

        if not negocios:
            logging.warning(f"Nenhum negócio encontrado para {numero} com responsável {responsavel_id}")
            return {"status": "no deal"}

        negocio_id = negocios[0]['ID']

        # Criar atividade de ligação no negócio
        await client.post(f"{BITRIX_WEBHOOK_BASE}/crm.activity.add", json={
            "fields": {
                "TYPE_ID": 2,  # Tipo chamada
                "SUBJECT": f"Ligação recebida via Uniq - {data.get('data_hora')}",
                "COMMUNICATIONS": [{
                    "ENTITY_ID": contato_id,
                    "ENTITY_TYPE_ID": 3  # Tipo contato
                }],
                "BINDINGS": [{
                    "OWNER_ID": negocio_id,
                    "OWNER_TYPE_ID": 2  # Tipo negócio
                }],
                "RESPONSIBLE_ID": responsavel_id,
                "DESCRIPTION": f"{data.get('descricao', '')}",
                "DESCRIPTION_TYPE": 3  # Texto
            }
        })

    logging.info(f"Atividade adicionada ao negócio {negocio_id}")
    return {"status": "ok"}
