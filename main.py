import json
import logging
import time
from datetime import datetime, timezone, timedelta

import pytz
import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)

BITRIX_WEBHOOK = "https://b24-rwd8iz.bitrix24.com.br/rest/94/as72rxtjh98pszj4/"

class CallData(BaseModel):
    numero: str
    duracao: int
    resultado: int

def buscar_negocio_por_telefone(telefone: str):
    url = f"{BITRIX_WEBHOOK}/crm.deal.list"
    params = {
        "filter[TYPE_ID]": "PHONE",
        "filter[PHONE]": telefone,
        "select[]": ["ID"]
    }
    res = requests.get(url, params=params)
    data = res.json()
    return data["result"][0] if data["result"] else None

def criar_atividade_chamada(deal_id: int, telefone: str, duracao: int, resultado: int):
    payload = {
        "fields": {
            "TYPE_ID": "CALL",
            "SUBJECT": f"Ligação recebida de {telefone}",
            "COMPLETED": "Y",
            "RESPONSIBLE_ID": 1,  # Atualize conforme necessário
            "ASSOCIATED_ENTITY_ID": deal_id,
            "ASSOCIATED_ENTITY_TYPE": "deal",
            "DURATION": duracao,
            "DESCRIPTION": f"Resultado: {resultado}"
        }
    }
    url = f"{BITRIX_WEBHOOK}/crm.activity.add"
    res = requests.post(url, json=payload)
    return res.json()

@app.post("/webhook")
async def receber_dados(request: Request):
    dados = await request.json()
    logging.info(f"Atividade registrada: {dados}")

    telefone = dados.get("numero")
    duracao = dados.get("duracao")
    resultado = dados.get("resultado")

    if telefone:
        negocio = buscar_negocio_por_telefone(telefone)
        if negocio:
            criar_atividade_chamada(negocio["ID"], telefone, duracao, resultado)

    return {"status": "ok"}
