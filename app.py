import streamlit as st
import pandas as pd
import hashlib
from datetime import datetime
import time

from google.oauth2 import service_account
from gspread.exceptions import WorksheetNotFound

import gspread

# ============================================================
# CONFIGURAÇÃO INICIAL
# ============================================================
st.set_page_config(page_title="URB Fiscalização", layout="wide")

# Nomes das abas na Planilha
SHEET_DENUNCIAS = "denuncias_registro"
SHEET_REINCIDENCIAS = "reincidencias"
SHEET_USUARIOS = "usuarios"  # Nova aba para persistir senhas

# Listas do Sistema
OPCOES_STATUS = ['Pendente', 'Em Andamento', 'Concluída', 'Arquivada']
OPCOES_ORIGEM = ['Pessoalmente','Telefone','Whatsapp','Ministério Publico','Administração','Ouvidoria','Disk Denuncia']
OPCOES_TIPO = ['Urbana','Ambiental','Urbana e Ambiental']
OPCOES_ZONA = ['NORTE','SUL','LESTE','OESTE','CENTRO']
# A lista de fiscais para o selectbox (pode ser diferente dos usuários de login)
OPCOES_FISCAIS_SELECT = ['EDVALDO','PATRICIA','RAIANY','SUELLEN']

# Schemas
DENUNCIA_SCHEMA = [
    'id', 'external_id', 'created_at', 'origem', 'tipo', 'rua', 
    'numero', 'bairro', 'zona', 'latitude', 'longitude', 
    'descricao', 'quem_recebeu', 'status', 'acao_noturna'
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
                # Correção de quebra de linha na chave privada
                if "private_key" in info:
                    info["private_key"] = info["private_key"].replace("\\n", "\n")

                creds = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=["https://www.googleapis.com/auth/spreadsheets"]
                )
                cls._gc = gspread.authorize(creds)
            except Exception as e:
                st.error(f"Erro no Login do Google Sheets: {e}")
                return None
        return cls._gc, cls._spreadsheet_key

# ============================================================
# FUNÇÕES DE BANCO DE DADOS (SHEETS)
# ============================================================

def get_worksheet(sheet_name):
    gc, key = SheetsClient.get_client()
    sh = gc.open_by_key(key)
    try:
        ws = sh.worksheet(sheet_name)
    except WorksheetNotFound:
        ws = sh.add_worksheet(sheet_name, rows=100, cols=20)
        # Cria cabeçalho se for nova
        if sheet_name == SHEET_DENUNCIAS:
            ws.append_row(DENUNCIA_SCHEMA)
        elif sheet_name == SHEET_USUARIOS:
            ws.append_row(["username", "password", "name", "role"])
    return ws

def load_data(sheet_name):
    """Lê os dados e retorna um DataFrame limpo"""
    ws = get_worksheet(sheet_name)
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    # Tratamento crucial para evitar erros de JSON depois
    return df.fillna('')

def add_row(sheet_name, row_dict, schema_order=None):
    """Adiciona uma linha nova usando append (Mais seguro contra concorrência)"""
    ws = get_worksheet(sheet_name)
    
    if schema_order:
        # Garante a ordem das colunas
        values = [str(row_dict.get(col, '')) for col in schema_order]
    else:
        values = [str(v) for v in row_dict.values()]
        
    ws.append_row(values)

def update_full_sheet(sheet_name, df):
    """Atualiza a planilha inteira (Usar apenas para edições/deleções)"""
    ws = get_worksheet(sheet_name)
    ws.clear()
    # Converte NaN para string vazia antes de enviar
    df_clean = df.fillna('')
    # Envia cabeçalho + dados
    ws.update([df_clean.columns.tolist()] + df_clean.values.tolist())

# ============================================================
# AUTENTICAÇÃO E USUÁRIOS
# ============================================================

def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def init_users_if_empty():
    """Cria os usuários padrão na planilha se a aba estiver vazia"""
    df_users = load_data(SHEET_USUARIOS)
    
    if df_users.empty:
        st.warning("Inicializando usuários padrão na planilha...")
        default_pwd = hash_password("urb123")
        
        # Lista fixa solicitada
        users_init = [
            {"username": "suellen", "password": default_pwd, "name": "Suellen", "role": "admin"},
            {"username": "edvaldo", "password": default_pwd, "name": "Edvaldo", "role": "user"},
            {"username": "patricia", "password": default_pwd, "name": "Patricia", "role": "user"},
            {"username": "raiany", "password": default_pwd, "name": "Raiany", "role": "user"},
        ]
        
        # Salva na planilha
        df_new = pd.DataFrame(users_init)
        update_full_sheet(SHEET_USUARIOS, df_new)
        return df_new
    return df_users

def check_login(username, password):
    df_users = init_users_if_empty() # Garante que existem usuários
    hashed = hash_password(password)
    
    user = df_users[
        (df_users['username'] == username.lower()) & 
        (df_users['password'] == hashed)
    ]
    
    if not user.empty:
        return user.iloc[0].to_dict()
    return None

def change_password(username, new_password):
    df_users = load_data(SHEET_USUARIOS)
    new_hash = hash_password(new_password)
    
    # Atualiza o dataframe
    df_users.loc[df_users['username'] == username, 'password'] = new_hash
    
    # Salva na planilha
    update_full_sheet(SHEET_USUARIOS, df_users)
    return True

# ============================================================
# INTERFACE - LOGIN
# ============================================================
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 URB Fiscalização")
        st.markdown("Login de Acesso")
        
        with st.form("login_form"):
            u = st.text_input("Usuário").strip()
            p = st.text_input("Senha", type="password")
            
            if st.form_submit_button("Entrar"):
                user_data = check_login(u, p)
                if user_data:
                    st.session_state.user = user_data
                    st.success(f"Bem-vindo(a), {user_data['name']}!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")
                    st.info("A senha padrão inicial é 'urb123'")
    st.stop() # Para a execução aqui se não estiver logado

# ============================================================
# INTERFACE - SIDEBAR
# ============================================================
user_info = st.session_state.user

st.sidebar.title(f"Olá, {user_info['name']}")
st.sidebar.caption(f"Perfil: {user_info['role']}")

page = st.sidebar.radio("Navegação", ["Dashboard", "Registrar Denúncia", "Histórico / Editar", "Reincidências"])

st.sidebar.divider()

# --- Alterar Senha ---
with st.sidebar.expander("🔑 Alterar Minha Senha"):
    with st.form("change_pwd"):
        new_p1 = st.text_input("Nova Senha", type="password")
        new_p2 = st.text_input("Confirmar Senha", type="password")
        if st.form_submit_button("Atualizar"):
            if new_p1 == new_p2 and len(new_p1) > 0:
                change_password(user_info['username'], new_p1)
                st.success("Senha alterada! Faça login novamente.")
                st.session_state.user = None
                time.sleep(2)
                st.rerun()
            else:
                st.error("Senhas não conferem ou vazias.")

if st.sidebar.button("Sair"):
    st.session_state.user = None
    st.rerun()

# ============================================================
# PÁGINA 1: DASHBOARD
# ============================================================
if page == "Dashboard":
    st.title("📊 Visão Geral")
    df = load_data(SHEET_DENUNCIAS)
    
    if not df.empty and 'status' in df.columns:
        cols = st.columns(4)
        cols[0].metric("Total", len(df))
        cols[1].metric("Pendentes", len(df[df['status'] == 'Pendente']))
        cols[2].metric("Em Andamento", len(df[df['status'] == 'Em Andamento']))
        cols[3].metric("Concluídas", len(df[df['status'] == 'Concluída']))
        
        st.divider()
        st.subheader("Últimas Denúncias")
        st.dataframe(df.tail(5)[['external_id', 'bairro', 'descricao', 'status']], use_container_width=True)
    else:
        st.info("Nenhuma denúncia registrada ainda.")

# ============================================================
# PÁGINA 2: REGISTRO
# ============================================================
elif page == "Registrar Denúncia":
    st.title("📝 Nova Denúncia")
    
    with st.form('registro'):
        col1, col2 = st.columns(2)
        origem = col1.selectbox('Origem', OPCOES_ORIGEM)
        tipo = col2.selectbox('Tipo', OPCOES_TIPO)
        
        rua = st.text_input('Rua')
        c1, c2, c3 = st.columns(3)
        numero = c1.text_input('Número')
        bairro = c2.text_input('Bairro')
        zona = c3.selectbox('Zona', OPCOES_ZONA)
        
        descricao = st.text_area('Descrição da Ocorrência')
        quem = st.selectbox('Quem recebeu a denúncia', OPCOES_FISCAIS_SELECT)
        
        if st.form_submit_button('💾 Salvar Denúncia'):
            if not rua or not descricao:
                st.error("Rua e Descrição são obrigatórios.")
            else:
                # Gera ID
                df = load_data(SHEET_DENUNCIAS)
                new_id = len(df) + 1
                ext_id = f"{new_id:04d}/{datetime.now().year}"
                
                record = {
                    'id': new_id,
                    'external_id': ext_id,
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'origem': origem,
                    'tipo': tipo,
                    'rua': rua,
                    'numero': numero,
                    'bairro': bairro,
                    'zona': zona,
                    'latitude': '',
                    'longitude': '',
                    'descricao': descricao,
                    'quem_recebeu': quem,
                    'status': 'Pendente',
                    'acao_noturna': 'FALSE'
                }
                
                # Usa APPEND (Mais seguro)
                add_row(SHEET_DENUNCIAS, record, DENUNCIA_SCHEMA)
                st.success(f"Denúncia {ext_id} registrada com sucesso!")
                time.sleep(1)
                st.rerun()

# ============================================================
# PÁGINA 3: HISTÓRICO E EDIÇÃO
# ============================================================
elif page == "Histórico / Editar":
    st.title("🗂️ Gerenciar Denúncias")
    df = load_data(SHEET_DENUNCIAS)
    
    if df.empty:
        st.info("Sem dados.")
        st.stop()

    # --- MODO DE EDIÇÃO (Lógica corrigida) ---
    if 'edit_id' in st.session_state:
        st.markdown("---")
        st.subheader(f"✏️ Editando ID: {st.session_state.edit_id}")
        
        # Filtra a linha segura
        try:
            row_idx = df.index[df['id'] == st.session_state.edit_id].tolist()[0]
            row_data = df.iloc[row_idx]
            
            with st.form("edit_form"):
                # Campos editáveis
                new_status = st.selectbox("Status", OPCOES_STATUS, index=OPCOES_STATUS.index(row_data['status']) if row_data['status'] in OPCOES_STATUS else 0)
                new_desc = st.text_area("Descrição", value=row_data['descricao'])
                
                col_save, col_cancel = st.columns(2)
                
                save = col_save.form_submit_button("✅ Salvar Alterações")
                # Botão cancelar fora do form é complicado, usando lógica simples:
                
                if save:
                    # Atualiza DataFrame
                    df.at[row_idx, 'status'] = new_status
                    df.at[row_idx, 'descricao'] = new_desc
                    
                    # Salva TUDO no sheets
                    update_full_sheet(SHEET_DENUNCIAS, df)
                    
                    st.success("Atualizado!")
                    del st.session_state.edit_id
                    time.sleep(1)
                    st.rerun()

            if st.button("Cancelar Edição"):
                del st.session_state.edit_id
                st.rerun()
                
        except IndexError:
            st.error("Erro ao encontrar registro. Tente recarregar.")
            del st.session_state.edit_id

        st.markdown("---")

    # --- LISTAGEM ---
    # Inverte para mostrar as mais recentes primeiro
    df_display = df.sort_values(by='id', ascending=False)
    
    for idx, row in df_display.iterrows():
        with st.container(border=True):
            cols = st.columns([1, 3, 1, 1])
            cols[0].markdown(f"**{row['external_id']}**")
            cols[0].caption(row['created_at'])
            
            cols[1].write(f"📍 {row['rua']}, {row['numero']} - {row['bairro']}")
            cols[1].caption(f"{row['tipo']} | {row['descricao'][:60]}...")
            
            # Badge de Status
            status_color = "orange" if row['status'] == "Pendente" else "green" if row['status'] == "Concluída" else "blue"
            cols[2].markdown(f":{status_color}[{row['status']}]")
            
            if cols[3].button("Editar", key=f"btn_edit_{row['id']}"):
                st.session_state.edit_id = row['id']
                st.rerun()

# ============================================================
# PÁGINA 4: REINCIDÊNCIAS
# ============================================================
elif page == "Reincidências":
    st.title("🔄 Registro de Reincidência")
    
    # Selecionar a denúncia original
    df_denuncias = load_data(SHEET_DENUNCIAS)
    
    if df_denuncias.empty:
        st.warning("Não há denúncias para gerar reincidência.")
    else:
        # Cria uma lista formatada para o selectbox
        df_denuncias['display_label'] = df_denuncias['external_id'] + " - " + df_denuncias['rua']
        
        escolha = st.selectbox("Selecione a Denúncia Original", df_denuncias['display_label'].tolist())
        
        if escolha:
            # Pega o ID externo real
            id_real = escolha.split(" - ")[0]
            
            with st.form("form_reincidencia"):
                st.write(f"Vinculando nova ocorrência ao processo: **{id_real}**")
                desc_reinc = st.text_area("Descrição da Reincidência / Nova Visita")
                origem_reinc = st.selectbox("Origem", OPCOES_ORIGEM)
                
                if st.form_submit_button("Registrar Reincidência"):
                    new_reinc = {
                        "external_id": id_real,
                        "data_hora": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "origem": origem_reinc,
                        "descricao": desc_reinc,
                        "registrado_por": user_info['name']
                    }
                    add_row(SHEET_REINCIDENCIAS, new_reinc)
                    st.success("Reincidência gravada!")















