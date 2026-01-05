import streamlit as st
import pandas as pd
import hashlib
from datetime import datetime
import time
import pytz

from google.oauth2 import service_account
from gspread.exceptions import WorksheetNotFound
import gspread
from fpdf import FPDF

# ============================================================
# CONFIGURAÇÃO INICIAL E FUSO
# ============================================================
st.set_page_config(page_title="URB Fiscalização", layout="wide")
FUSO_BR = pytz.timezone('America/Recife')

# Nomes das abas
SHEET_DENUNCIAS = "denuncias_registro"
SHEET_REINCIDENCIAS = "reincidencias"
SHEET_USUARIOS = "usuarios"

# Listas
OPCOES_STATUS = ['Pendente', 'Em Andamento', 'Concluída', 'Arquivada']
OPCOES_ORIGEM = ['Pessoalmente', 'Telefone', 'Whatsapp', 'Ministério Publico', 'Administração', 'Ouvidoria', 'Disk Denuncia']
OPCOES_TIPO = ['Urbana', 'Ambiental', 'Urbana e Ambiental']
OPCOES_ZONA = ['NORTE', 'SUL', 'LESTE', 'OESTE', 'CENTRO']
OPCOES_FISCAIS_SELECT = ['Edvaldo Wilson Bezerra da Silva - 000.323', 'PATRICIA MIRELLY BEZERRA CAMPOS - 000.332', 'Raiany Nayara de Lima - 000.362', 'Suellen Bezerra do Nascimeto - 000.417']

# SCHEMAS (Apenas referência, agora o salvamento é dinâmico)
DENUNCIA_SCHEMA = [
    'id', 'external_id', 'created_at', 'origem', 'tipo', 'rua', 
    'numero', 'bairro', 'zona', 'latitude', 'longitude', 
    'descricao', 'quem_recebeu', 'status', 'acao_noturna'
]

REINCIDENCIA_SCHEMA = [
    'external_id', 'data_hora', 'origem', 'descricao', 'registrado_por'
]

# ============================================================
# CONEXÃO GOOGLE SHEETS
# ============================================================
class SheetsClient:
    _gc = None
    _spreadsheet_key = None

    @classmethod
    def get_client(cls):
        if cls._gc is None:
            try:
                secrets = st.secrets["gcp_service_account"]
                cls._spreadsheet_key = secrets["spreadsheet_key"]
                
                info = dict(secrets)
                if "private_key" in info:
                    info["private_key"] = info["private_key"].replace("\\n", "\n")

                creds = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=["https://www.googleapis.com/auth/spreadsheets"]
                )
                cls._gc = gspread.authorize(creds)
            except Exception as e:
                st.error(f"Erro no Login do Google Sheets: {e}")
                return None, None
        return cls._gc, cls._spreadsheet_key

# ============================================================
# FUNÇÃO GERADORA DE PDF (CORRIGIDA VISUALMENTE)
# ============================================================
def clean_text(text):
    if text is None: return ""
    return str(text).encode('latin-1', 'replace').decode('latin-1')

def gerar_pdf(dados):
    pdf = FPDF()
    pdf.add_page()
    
    # --- TRATAMENTO DE ERROS DE DADOS ANTIGOS ---
    status_display = str(dados.get('status', ''))
    fiscal_display = str(dados.get('quem_recebeu', ''))
    
    # Se o status estiver como FALSE (erro de coluna), força Pendente
    if status_display.upper() == 'FALSE':
        status_display = "Pendente"
        
    # Se o fiscal estiver como Pendente (coluna trocada), tenta limpar
    if fiscal_display in OPCOES_STATUS: 
        fiscal_display = "Nao Informado (Erro Cadastro)"

    # Cabeçalho
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, clean_text(f"ORDEM DE SERVICO - {dados['external_id']}"), ln=True, align='C')
    pdf.line(10, 20, 200, 20)
    pdf.ln(10)
    
    # Dados
    pdf.set_font("Arial", size=12)
    campos = [
        ("Data Abertura", dados.get('created_at', '')),
        ("Status Atual", status_display),  # Usa a variável corrigida
        ("Tipo", dados.get('tipo
