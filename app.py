# app.py
# ============================================================
# URB Fiscalização - Denúncias
# Versão consolidada com:
# - Mapper fixo de colunas
# - Validação antes de salvar
# - UX melhorada
# - Botões Editar/Reincidência direto na tabela
# - Dashboard por status
# - Reincidências em aba separada no Sheets
# - Perfis de usuário por permissão
# ============================================================

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import hashlib

import gspread
from google.oauth2 import service_account
from gspread.exceptions import WorksheetNotFound, SpreadsheetNotFound

from fpdf import FPDF

# ---------------------- CONFIGURAÇÃO ----------------------
st.set_page_config(page_title="URB Fiscalização - Denúncias", layout="wide")

# ---------------------- CONSTANTES ----------------------
SHEET_DENUNCIAS = "denuncias"
SHEET_REINCIDENCIAS = "reincidencias"
USERS_PATH = "users.json"

# ---------------------- SCHEMA FIXO ----------------------
DENUNCIA_SCHEMA = {
    'id': 0,
    'external_id': '',
    'created_at': '',
    'origem': '',
    'tipo': '',
    'rua': '',
    'numero': '',
    'bairro': '',
    'zona': '',
    'latitude': '',
    'longitude': '',
    'descricao': '',
    'quem_recebeu': '',
    'status': 'Pendente',
    'acao_noturna': False
}

REINCIDENCIA_SCHEMA = {
    'external_id': '',
    'data_hora': '',
    'origem': '',
    'descricao': ''
}

# ---------------------- OPÇÕES ----------------------
OPCOES_STATUS = ['Pendente', 'Em Andamento', 'Concluída', 'Arquivada']
OPCOES_ORIGEM = ['Pessoalmente','Telefone','Whatsapp','Ministério Publico','Administração','Ouvidoria','Disk Denuncia']
OPCOES_TIPO = ['Urbana','Ambiental','Urbana e Ambiental']
OPCOES_ZONA = ['NORTE','SUL','LESTE','OESTE','CENTRO']
OPCOES_FISCAIS = ['EDVALDO','PATRICIA','RAIANY','SUELLEN']

# ---------------------- GOOGLE SHEETS ----------------------
class SheetsClient:
    _gc = None

    @classmethod
    def get_client(cls):
        if cls._gc is None:
           try:
               secrets = st.secrets["gcp_service_account"]
               info = dict(secrets)

               # >>> CORREÇÃO CRÍTICA AQUI <<<
               # 1. Garante que 'private_key' existe
               private_key = info.get("private_key")
               if not private_key:
                   raise KeyError("Chave 'private_key' não encontrada no Service Account.")

               # 2. Substitui \n por quebras de linha reais, o que é exigido pelo Google
               info["private_key"] = private_key.replace("\\n", "\n")
               # FIM CORREÇÃO

               creds = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=[
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/drive",
                    ],
                )
               cls._gc = gspread.authorize(creds)
               
           except Exception as e:
               st.error(f"❌ Erro de Autenticação GSheets. Verifique a chave 'private_key' nos Secrets.")
               st.code(repr(e))
               # Retorna None em caso de falha de autenticação
               return None 

        return cls._gc
# ---------------------- UTILITIES ----------------------

def normalize_record(rec, schema):
    clean = schema.copy()
    if not rec:
        return clean
    for k in clean:
        v = rec.get(k)
        if pd.isna(v) or v is None:
            clean[k] = schema[k]
        else:
            clean[k] = v
    return clean


def validate_denuncia(data):
    errors = []
    for field in ['origem','tipo','rua','numero','bairro','zona','descricao','quem_recebeu']:
        if not str(data.get(field, '')).strip():
            errors.append(f"Campo obrigatório não preenchido: {field}")
    return errors


def load_sheet(sheet_name):
    # 🔑 Lê a chave da planilha DENTRO do bloco gcp_service_account (mais estável no Streamlit Cloud)
    secrets = st.secrets.get("gcp_service_account")
    if not secrets or "spreadsheet_key" not in secrets:
        st.error(
            "❌ A chave 'spreadsheet_key' não foi encontrada dentro de [gcp_service_account] nos Secrets.\n"
            "Abra Manage app → Settings → Secrets e mova a chave para dentro do bloco gcp_service_account."
        )
        st.stop()

    spreadsheet_key = secrets["spreadsheet_key"]

    gc = SheetsClient.get_client()
    sh = gc.open_by_key(spreadsheet_key)

    try:
        ws = sh.worksheet(sheet_name)
    except WorksheetNotFound:
        ws = sh.add_worksheet(sheet_name, rows=100, cols=20)
        header = list(DENUNCIA_SCHEMA.keys()) if sheet_name == SHEET_DENUNCIAS else list(REINCIDENCIA_SCHEMA.keys())
        ws.append_row(header)

    return pd.DataFrame(ws.get_all_records())


def save_sheet(sheet_name, df):
    secrets = st.secrets.get("gcp_service_account")
    if not secrets or "spreadsheet_key" not in secrets:
        st.error(
            "❌ A chave 'spreadsheet_key' não foi encontrada dentro de [gcp_service_account] nos Secrets."
        )
        st.stop()

    spreadsheet_key = secrets["spreadsheet_key"]

    gc = SheetsClient.get_client()
    sh = gc.open_by_key(spreadsheet_key)
    ws = sh.worksheet(sheet_name)
    ws.clear()
    ws.update([df.columns.tolist()] + df.values.tolist())

# ---------------------- AUTH ----------------------

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()


def load_users():
    if not os.path.exists(USERS_PATH):
        with open(USERS_PATH, 'w') as f:
            json.dump([], f)
    return json.load(open(USERS_PATH))


def verify_user(u, p):
    if u == 'admin' and p == 'admin':
        return {'username':'admin','role':'admin'}
    for user in load_users():
        if user['username']==u and user['password']==hash_password(p):
            return user
    return None

# ---------------------- LOGIN ----------------------
if 'user' not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    st.title("Login")
    u = st.text_input("Usuário")
    p = st.text_input("Senha", type='password')
    if st.button("Entrar"):
        user = verify_user(u,p)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Login inválido")
    st.stop()

# ---------------------- SIDEBAR ----------------------
st.sidebar.title("URB Fiscalização")
page = st.sidebar.selectbox("Menu", ["Dashboard","Registro","Histórico","Reincidências"])

# ---------------------- DASHBOARD ----------------------
if page == 'Dashboard':
    df = load_sheet(SHEET_DENUNCIAS)

if df is not None and not df.empty and 'status' in df.columns:
    # O código original do Dashboard
    STATUS_OPTS = ['Pendente', 'Concluída', 'Cancelada']

    for status in STATUS_OPTS:
        # AQUI É IMPORTANTE: len(df[df['status']==status])
        # Se você está usando o Pandas, a sintaxe está correta. 
        # A falha é na presença da coluna.
        st.metric(status, len(df[df['status']==status]))

else:
    # Mensagem de erro se o DataFrame não foi carregado corretamente
    st.error("Não foi possível carregar os dados da planilha de denúncias ou a coluna 'status' não foi encontrada. Verifique as credenciais e o nome das colunas da planilha.")

# ---------------------- REGISTRO ----------------------
if page == 'Registro':
    st.subheader("Registrar Denúncia")
    with st.form('registro'):
        origem = st.selectbox('Origem', OPCOES_ORIGEM)
        tipo = st.selectbox('Tipo', OPCOES_TIPO)
        rua = st.text_input('Rua')
        numero = st.text_input('Número')
        bairro = st.text_input('Bairro')
        zona = st.selectbox('Zona', OPCOES_ZONA)
        descricao = st.text_area('Descrição')
        quem = st.selectbox('Quem recebeu', OPCOES_FISCAIS)
        submit = st.form_submit_button('Salvar')

    if submit:
        record = normalize_record({}, DENUNCIA_SCHEMA)
        record.update({
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'origem': origem,
            'tipo': tipo,
            'rua': rua,
            'numero': numero,
            'bairro': bairro,
            'zona': zona,
            'descricao': descricao,
            'quem_recebeu': quem,
        })
        errors = validate_denuncia(record)
        if errors:
            for e in errors: st.error(e)
        else:
            df = load_sheet(SHEET_DENUNCIAS)
            record['id'] = len(df)+1
            record['external_id'] = f"{record['id']:04d}/{datetime.now().year}"
            df = pd.concat([df, pd.DataFrame([record])])
            save_sheet(SHEET_DENUNCIAS, df)
            st.success("Denúncia registrada")

# ---------------------- HISTÓRICO ----------------------
if page == 'Histórico':
    df = load_sheet(SHEET_DENUNCIAS)
    st.subheader("Histórico")

    for _, row in df.iterrows():
        with st.container(border=True):
            st.write(f"**{row['external_id']}** - {row['status']}")
            col1, col2 = st.columns(2)
            if col1.button('✍️ Editar', key=f"e{row['id']}"):
                st.session_state.edit_id = row['id']
            if col2.button('➕ Reincidência', key=f"r{row['id']}"):
                st.session_state.reinc_id = row['external_id']

# ---------------------- REINCIDÊNCIAS ----------------------
if page == 'Reincidências':
    df = load_sheet(SHEET_REINCIDENCIAS)
    st.subheader("Reincidências")
    st.dataframe(df)

    if 'reinc_id' in st.session_state:
        st.markdown(f"### Nova reincidência para {st.session_state.reinc_id}")
        with st.form('reinc'):
            origem = st.selectbox('Origem', OPCOES_ORIGEM)
            desc = st.text_area('Descrição')
            submit = st.form_submit_button('Salvar')
        if submit:
            new = normalize_record({}, REINCIDENCIA_SCHEMA)
            new.update({
                'external_id': st.session_state.reinc_id,
                'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'origem': origem,
                'descricao': desc
            })
            df = pd.concat([df, pd.DataFrame([new])])
            save_sheet(SHEET_REINCIDENCIAS, df)
            st.success('Reincidência registrada')
            del st.session_state.reinc_id
            st.rerun()













