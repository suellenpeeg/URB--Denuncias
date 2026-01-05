import streamlit as st
import pandas as pd
import hashlib
from datetime import datetime
import time

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
OPCOES_ORIGEM = ['Pessoalmente','Telefone','Whatsapp','Ministério Publico','Administração','Ouvidoria','Disk Denuncia']
OPCOES_TIPO = ['Urbana','Ambiental','Urbana e Ambiental']
OPCOES_ZONA = ['NORTE','SUL','LESTE','OESTE','CENTRO']
OPCOES_FISCAIS_SELECT = ['Edvaldo Wilson Bezerra da Silva - 000.323','PATRICIA MIRELLY BEZERRA CAMPOS - 000.332','Raiany Nayara de Lima - 000.362','Suellen Bezerra do Nascimeto - 000.417']

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
        ("Status Atual", status_display),  # Usa a variável corrigida
        ("Tipo", dados.get('tipo', '')),
        ("Origem", dados.get('origem', '')),
        ("Fiscal Responsavel", fiscal_display), # Usa a variável corrigida
        ("Endereco", f"{dados.get('rua','')} , {dados.get('numero','')} - {dados.get('bairro','')}"),
        ("Zona", dados.get('zona', '')),
    ]
    for titulo, valor in campos:
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(50, 10, clean_text(f"{titulo}:"), border=0)
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, clean_text(valor), ln=True)
        
    pdf.ln(5)
    
    # Descrição
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, clean_text("Relato / Historico:"), ln=True)
    pdf.set_font("Arial", '', 12)
    pdf.multi_cell(0, 7, clean_text(dados.get('descricao', '')))
    
    pdf.ln(20)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.cell(0, 10, clean_text("Assinatura do Responsavel"), align='R')
    
    # Output seguro
    pdf_content = pdf.output(dest='S')
    if isinstance(pdf_content, str):
        return pdf_content.encode('latin-1')
    return bytes(pdf_content)

# ============================================================
# FUNÇÕES DE BANCO DE DADOS (AGORA INTELIGENTES)
# ============================================================
def get_worksheet(sheet_name):
    gc, key = SheetsClient.get_client()
    if not gc: return None
    
    sh = gc.open_by_key(key)
    try:
        ws = sh.worksheet(sheet_name)
    except WorksheetNotFound:
        ws = sh.add_worksheet(sheet_name, rows=100, cols=20)
        # Cria cabeçalho inicial se não existir
        if sheet_name == SHEET_DENUNCIAS:
            ws.append_row(DENUNCIA_SCHEMA)
        elif sheet_name == SHEET_USUARIOS:
            ws.append_row(["username", "password", "name", "role"])
        elif sheet_name == SHEET_REINCIDENCIAS:
            ws.append_row(REINCIDENCIA_SCHEMA)
    return ws

def load_data(sheet_name):
    ws = get_worksheet(sheet_name)
    if not ws: return pd.DataFrame()
    data = ws.get_all_records() # Isso lê os headers reais da planilha
    df = pd.DataFrame(data)
    return df.fillna('')

def salvar_dados_seguro(sheet_name, row_dict):
    """
    Função INTELIGENTE: Lê a ordem das colunas da planilha e salva no lugar certo.
    Isso evita o erro de 'Status' cair na coluna 'Fiscal'.
    """
    ws = get_worksheet(sheet_name)
    
    # 1. Pega os cabeçalhos que REALMENTE estão na planilha
    headers = ws.row_values(1)
    
    # 2. Se a planilha estiver vazia (sem header), usa o padrão
    if not headers:
        if sheet_name == SHEET_DENUNCIAS: headers = DENUNCIA_SCHEMA
        elif sheet_name == SHEET_REINCIDENCIAS: headers = REINCIDENCIA_SCHEMA
        ws.append_row(headers)
    
    # 3. Monta a lista de valores na ordem que a planilha pede
    values = []
    for h in headers:
        # Pega o valor correspondente ao cabeçalho, ou vazio se não tiver
        val = row_dict.get(h, '') 
        values.append(str(val))
        
    ws.append_row(values)

def update_full_sheet(sheet_name, df):
    ws = get_worksheet(sheet_name)
    ws.clear()
    df_clean = df.fillna('')
    ws.update([df_clean.columns.tolist()] + df_clean.values.tolist())

# ============================================================
# AUTENTICAÇÃO
# ============================================================
def hash_password(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def init_users_if_empty():
    df_users = load_data(SHEET_USUARIOS)
    if df_users.empty:
        st.warning("Criando usuários padrão...")
        default_pwd = hash_password("urb123")
        users_init = [
            {"username": "suellen", "password": default_pwd, "name": "Suellen", "role": "admin"},
            {"username": "edvaldo", "password": default_pwd, "name": "Edvaldo", "role": "user"},
            {"username": "patricia", "password": default_pwd, "name": "Patricia", "role": "user"},
            {"username": "raiany", "password": default_pwd, "name": "Raiany", "role": "user"},
        ]
        df_new = pd.DataFrame(users_init)
        update_full_sheet(SHEET_USUARIOS, df_new)
        return df_new
    return df_users

def check_login(username, password):
    df_users = init_users_if_empty()
    hashed = hash_password(password)
    user = df_users[(df_users['username'] == username.lower()) & (df_users['password'] == hashed)]
    return user.iloc[0].to_dict() if not user.empty else None

def change_password(username, new_password):
    df_users = load_data(SHEET_USUARIOS)
    new_hash = hash_password(new_password)
    df_users.loc[df_users['username'] == username, 'password'] = new_hash
    update_full_sheet(SHEET_USUARIOS, df_users)
    return True

# ============================================================
# TELA LOGIN
# ============================================================
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 URB Fiscalização")
        with st.form("login"):
            u = st.text_input("Usuário").strip()
            p = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                user_data = check_login(u, p)
                if user_data:
                    st.session_state.user = user_data
                    st.success(f"Olá, {user_data['name']}!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Login inválido")
    st.stop()

# ============================================================
# APP PRINCIPAL
# ============================================================
user_info = st.session_state.user
st.sidebar.title(f"Fiscal: {user_info['name']}")
page = st.sidebar.radio("Menu", ["Dashboard", "Registrar Denúncia", "Histórico / Editar", "Reincidências"])
st.sidebar.divider()

with st.sidebar.expander("🔑 Senha"):
    with st.form("pwd"):
        np = st.text_input("Nova Senha", type="password")
        if st.form_submit_button("Alterar"):
            if len(np) > 0:
                change_password(user_info['username'], np)
                st.success("Senha alterada! Relogue.")
                st.session_state.user = None
                time.sleep(2)
                st.rerun()

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
        # Correção visual para o Dashboard
        df['status'] = df['status'].replace('FALSE', 'Pendente').replace('False', 'Pendente')

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(df))
        c2.metric("Pendentes", len(df[df['status'] == 'Pendente']))
        c3.metric("Em Andamento", len(df[df['status'] == 'Em Andamento']))
        c4.metric("Concluídas", len(df[df['status'] == 'Concluída']))
        
        st.subheader("Últimas Ocorrências")
        st.dataframe(df.tail(5)[['external_id','bairro','status']], use_container_width=True)
    else:
        st.info("Sem dados.")

# ============================================================
# PÁGINA 2: REGISTRO
# ============================================================
elif page == "Registrar Denúncia":
    st.title("📝 Nova Denúncia")
    with st.form('reg'):
        c1, c2 = st.columns(2)
        origem = c1.selectbox('Origem', OPCOES_ORIGEM)
        tipo = c2.selectbox('Tipo', OPCOES_TIPO)
        rua = st.text_input('Rua')
        c3, c4, c5 = st.columns(3)
        numero = c3.text_input('Número')
        bairro = c4.text_input('Bairro')
        zona = c5.selectbox('Zona', OPCOES_ZONA)
        desc = st.text_area('Descrição')
        quem = st.selectbox('Quem recebeu', OPCOES_FISCAIS_SELECT)
        
        if st.form_submit_button('💾 Salvar'):
            if not rua:
                st.error("Rua obrigatória.")
            else:
                df = load_data(SHEET_DENUNCIAS)
                new_id = len(df) + 1
                ext_id = f"{new_id:04d}/{datetime.now().year}"
                agora_br = datetime.now(FUSO_BR).strftime('%Y-%m-%d %H:%M:%S')
                
                record = {
                    'id': new_id,
                    'external_id': ext_id,
                    'created_at': agora_br,
                    'origem': origem,
                    'tipo': tipo,
                    'rua': rua,
                    'numero': numero,
                    'bairro': bairro,
                    'zona': zona,
                    'latitude': '',
                    'longitude': '',
                    'descricao': desc,
                    'quem_recebeu': quem, # Garante que vai pra coluna certa
                    'status': 'Pendente',
                    'acao_noturna': 'FALSE'
                }
                # USA A FUNÇÃO NOVA E SEGURA
                salvar_dados_seguro(SHEET_DENUNCIAS, record)
                st.success(f"Denúncia {ext_id} salva!")
                time.sleep(1)
                st.rerun()

# ============================================================
# PÁGINA 3: HISTÓRICO
# ============================================================
elif page == "Histórico / Editar":
    st.title("🗂️ Gerenciar")
    df = load_data(SHEET_DENUNCIAS)
    
    if df.empty:
        st.warning("Vazio.")
        st.stop()

    # Edição
    if 'edit_id' in st.session_state:
        st.markdown("---")
        st.info(f"✏️ Editando: {st.session_state.edit_id}")
        row_idx_list = df.index[df['id'] == st.session_state.edit_id].tolist()
        
        if row_idx_list:
            idx = row_idx_list[0]
            row_data = df.iloc[idx]
            
            with st.form("edit"):
                # Tratamento visual do erro FALSE
                curr_st = row_data.get('status', 'Pendente')
                if str(curr_st).upper() == 'FALSE': curr_st = 'Pendente'
                
                idx_st = OPCOES_STATUS.index(curr_st) if curr_st in OPCOES_STATUS else 0
                
                nst = st.selectbox("Status", OPCOES_STATUS, index=idx_st)
                ndesc = st.text_area("Descrição", value=row_data.get('descricao', ''), height=150)
                
                if st.form_submit_button("✅ Salvar"):
                    df.at[idx, 'status'] = nst
                    df.at[idx, 'descricao'] = ndesc
                    update_full_sheet(SHEET_DENUNCIAS, df)
                    st.success("Salvo!")
                    del st.session_state.edit_id
                    time.sleep(1)
                    st.rerun()
            if st.button("Cancelar"):
                del st.session_state.edit_id
                st.rerun()
        st.markdown("---")

    # Listagem
    df_display = df.sort_values(by='id', ascending=False)
    for idx, row in df_display.iterrows():
        with st.container(border=True):
            cols = st.columns([1, 3, 1.2, 0.6, 0.6])
            cols[0].markdown(f"**{row.get('external_id','')}**")
            cols[0].caption(row.get('created_at',''))
            
            cols[1].write(f"📍 {row.get('rua','')} - {row.get('bairro','')}")
            cols[1].caption(f"{row.get('tipo','')} | {str(row.get('descricao',''))[:50]}...")
            
            # Status Visual
            st_val = str(row.get('status',''))
            if st_val.upper() == 'FALSE':
                st_dsp = "Pendente"
                clr = "orange"
            else:
                st_dsp = st_val
                clr = "orange" if st_dsp == "Pendente" else "green" if st_dsp == "Concluída" else "blue"
            
            cols[2].markdown(f":{clr}[**{st_dsp}**]")
            
            # PDF
            try:
                pdf_bytes = gerar_pdf(row)
                cols[3].download_button("📄", pdf_bytes, f"OS_{row.get('external_id','').replace('/','-')}.pdf", "application/pdf", key=f"pdf_{row['id']}")
            except Exception as e:
                cols[3].error("Erro")
            
            if cols[4].button("✏️", key=f"btn_{row['id']}"):
                st.session_state.edit_id = row['id']
                st.rerun()

# ============================================================
# PÁGINA 4: REINCIDÊNCIAS
# ============================================================
elif page == "Reincidências":
    st.title("🔄 Reincidência")
    st.info("Adiciona relato e reabre o caso.")
    df_den = load_data(SHEET_DENUNCIAS)
    
    if not df_den.empty:
        df_den['label'] = df_den['external_id'].astype(str) + " - " + df_den['rua'].astype(str)
        escolha = st.selectbox("Denúncia Original", df_den['label'].tolist())
        
        if escolha:
            real_id = escolha.split(" - ")[0]
            row_idx = df_den.index[df_den['external_id'] == real_id].tolist()[0]
            desc_atual = df_den.at[row_idx, 'descricao']
            
            with st.expander("Ver Atual"): st.text(desc_atual)
            
            with st.form("reinc"):
                desc_nova = st.text_area("Novo Relato")
                origem = st.selectbox("Origem", OPCOES_ORIGEM)
                
                if st.form_submit_button("Salvar"):
                    if not desc_nova:
                        st.error("Escreva algo.")
                    else:
                        agora_br = datetime.now(FUSO_BR).strftime('%Y-%m-%d %H:%M:%S')
                        timestamp = datetime.now(FUSO_BR).strftime('%d/%m/%Y %H:%M')
                        
                        rec = {
                            "external_id": real_id,
                            "data_hora": agora_br,
                            "origem": origem,
                            "descricao": desc_nova,
                            "registrado_por": user_info['name']
                        }
                        salvar_dados_seguro(SHEET_REINCIDENCIAS, rec)
                        
                        texto_add = f"\n\n{'='*20}\n[REINCIDÊNCIA - {timestamp}]\nFiscal: {user_info['name']} | Origem: {origem}\n{desc_nova}"
                        df_den.at[row_idx, 'descricao'] = str(desc_atual) + texto_add
                        df_den.at[row_idx, 'status'] = 'Pendente'
                        
                        update_full_sheet(SHEET_DENUNCIAS, df_den)
                        st.success("Feito!")
                        time.sleep(2)
                        st.rerun()


































