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

# SCHEMAS
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
# NOVA FUNÇÃO GERADORA DE PDF (ESTILO FORMULÁRIO)
# ============================================================
def gerar_pdf(dados):
    class PDF(FPDF):
        def header(self):
            # Título Centralizado (Sem logo, conforme pedido)
            self.set_font('Arial', 'B', 14)
            self.cell(0, 6, clean_text("Autarquia de Urbanização e Meio Ambiente de Caruaru"), 0, 1, 'C')
            self.set_font('Arial', 'B', 12)
            self.cell(0, 6, clean_text("Central de Atendimento"), 0, 1, 'C')
            self.ln(5)

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # --- Configurações de Formatação ---
    pdf.set_line_width(0.3)
    
    def celula_cinza(texto):
        pdf.set_fill_color(220, 220, 220) # Cinza claro
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(0, 6, clean_text(texto), 1, 1, 'L', fill=True)

    # 1. Cabeçalho da OS
    celula_cinza(f"ORDEM DE SERVIÇO - SETOR {str(dados.get('tipo', '')).upper()}")
    
    # Linha de metadados: Nº, Data, Hora, Origem
    pdf.set_font("Arial", 'B', 9)
    
    # Tratamento de Data/Hora
    try:
        dt_obj = datetime.strptime(dados.get('created_at', ''), '%Y-%m-%d %H:%M:%S')
        data_fmt = dt_obj.strftime('%d/%m/%Y')
        hora_fmt = dt_obj.strftime('%H:%M')
    except:
        data_fmt = dados.get('created_at', '')
        hora_fmt = ""

    # Desenhando a linha de dados (Tabela manual para ajuste fino)
    y_start = pdf.get_y()
    
    # Coluna Nº
    pdf.cell(10, 8, "Nº", 1, 0, 'C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(30, 8, str(dados.get('external_id', '')), 1, 0, 'C')
    
    # Coluna Data
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(15, 8, "DATA:", 1, 0, 'C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(25, 8, data_fmt, 1, 0, 'C')

    # Coluna Hora
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(15, 8, "HORA:", 1, 0, 'C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(20, 8, hora_fmt, 1, 0, 'C')

    # Coluna Origem
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(20, 8, "ORIGEM:", 1, 0, 'L')
    pdf.set_font("Arial", '', 9)
    # Calcula largura restante
    largura_restante = 190 - (10+30+15+25+15+20+20) 
    pdf.cell(0, 8, clean_text(dados.get('origem', '')), 1, 1, 'L')

    # 2. Linha Bairro e Zona
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(40, 8, "BAIRRO OU DISTRITO:", 1, 0, 'L')
    pdf.set_font("Arial", '', 10)
    pdf.cell(110, 8, clean_text(dados.get('bairro', '')), 1, 0, 'L')
    
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(10, 8, "TGS:", 1, 0, 'C') # TGS refere-se à Zona/Setor
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 8, clean_text(dados.get('zona', '')), 1, 1, 'C')

    # 3. Descrição
    celula_cinza("DESCRIÇÃO DA ORDEM DE SERVIÇO")
    pdf.set_font("Arial", '', 10)
    # MultiCell para texto longo com quebra de linha
    pdf.multi_cell(0, 6, clean_text(dados.get('descricao', '')), 1, 'L')

    # 4. Local da Ocorrência
    celula_cinza("LOCAL DA OCORRÊNCIA")
    
    # Logradouro
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(30, 8, "LOGRADOURO:", "L,B", 0, 'L') # Bordas Esquerda e Baixo apenas
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 8, clean_text(dados.get('rua', '')), "R,B", 1, 'L') # Bordas Direita e Baixo
    
    # Número
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(30, 8, "Nº:", "L,B", 0, 'L')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 8, clean_text(dados.get('numero', '')), "R,B", 1, 'L')

    # Ponto de Referência / Obs (Campo Vazio para anotação ou dados extras)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(40, 8, clean_text("PONTO DE REFERÊNCIA:"), 1, 0, 'L')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 8, "", 1, 1, 'L')

    pdf.ln(3)

    # 5. Área de Assinatura (Quem Recebeu)
    # Caixa para o Fiscal
    y_sig = pdf.get_y()
    pdf.rect(10, y_sig, 140, 20) # Caixa Nome
    pdf.rect(150, y_sig, 50, 20) # Caixa Rubrica

    pdf.set_xy(12, y_sig + 2)
    pdf.set_font("Arial", 'B', 8)
    pdf.cell(0, 5, "RECEBIDO POR:", 0, 1)
    
    pdf.set_font("Arial", '', 11)
    pdf.set_xy(12, y_sig + 8)
    pdf.cell(135, 8, clean_text(dados.get('quem_recebeu', '')), 0, 0, 'C')

    pdf.set_xy(150, y_sig + 2)
    pdf.set_font("Arial", 'B', 8)
    pdf.cell(50, 5, "Rubrica", 0, 0, 'C')

    pdf.set_xy(10, y_sig + 25)

    # 6. Informações da Fiscalização (Para preenchimento manual em campo)
    celula_cinza("INFORMAÇÕES DA FISCALIZAÇÃO")
    
    # Linha de Data/Hora Manual
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(95, 8, "DATA DA VISTORIA: _____/_____/_______", 1, 0, 'L')
    pdf.cell(0, 8, "HORA: _____:_____", 1, 1, 'L')

    # Caixa Grande de Observações
    y_obs = pdf.get_y()
    pdf.rect(10, y_obs, 190, 50)
    
    pdf.set_xy(12, y_obs + 1)
    pdf.set_font("Arial", '', 8)
    pdf.cell(0, 5, clean_text("OBSERVAÇÕES E DESCRIÇÃO DA OCORRÊNCIA (CAMPO RESERVADO AO FISCAL)"), 0, 1)

    # Output
    pdf_content = pdf.output(dest='S')
    if isinstance(pdf_content, str):
        return pdf_content.encode('latin-1')
    return bytes(pdf_content)

# ============================================================
# FUNÇÕES DE BANCO DE DADOS
# ============================================================
def get_worksheet(sheet_name):
    gc, key = SheetsClient.get_client()
    if not gc: return None
    
    sh = gc.open_by_key(key)
    try:
        ws = sh.worksheet(sheet_name)
    except WorksheetNotFound:
        ws = sh.add_worksheet(sheet_name, rows=100, cols=20)
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
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    return df.fillna('')

def salvar_dados_seguro(sheet_name, row_dict):
    ws = get_worksheet(sheet_name)
    headers = ws.row_values(1)
    if not headers:
        if sheet_name == SHEET_DENUNCIAS: headers = DENUNCIA_SCHEMA
        elif sheet_name == SHEET_REINCIDENCIAS: headers = REINCIDENCIA_SCHEMA
        ws.append_row(headers)
    
    values = []
    for h in headers:
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
                    'id': new_id, 'external_id': ext_id, 'created_at': agora_br,
                    'origem': origem, 'tipo': tipo, 'rua': rua, 'numero': numero,
                    'bairro': bairro, 'zona': zona, 'latitude': '', 'longitude': '',
                    'descricao': desc, 'quem_recebeu': quem, 'status': 'Pendente',
                    'acao_noturna': 'FALSE'
                }
                salvar_dados_seguro(SHEET_DENUNCIAS, record)
                st.success(f"Denúncia {ext_id} salva!")
                time.sleep(1)
                st.rerun()

# ============================================================
# PÁGINA 3: HISTÓRICO (COM FILTROS E EXCLUSÃO)
# ============================================================
elif page == "Histórico / Editar":
    st.title("🗂️ Gerenciar Denúncias")
    
    # 1. Carregar dados
    df = load_data(SHEET_DENUNCIAS)
    
    if df.empty:
        st.warning("Nenhuma denúncia registrada.")
        st.stop()

    # --------------------------------------------------------
    # ÁREA DE FILTROS
    # --------------------------------------------------------
    st.markdown("### 🔍 Filtros de Pesquisa")
    
    # Garantir que as colunas existem para não dar erro no filtro
    if 'bairro' not in df.columns: df['bairro'] = ''
    if 'zona' not in df.columns: df['zona'] = ''
    if 'status' not in df.columns: df['status'] = ''

    c_filtro1, c_filtro2, c_filtro3, c_filtro4 = st.columns(4)
    
    with c_filtro1:
        filtro_texto = st.text_input("Buscar (ID ou Rua)", placeholder="Ex: 0001 ou Rua das Flores")
    with c_filtro2:
        lista_bairros = sorted(list(set(df['bairro'].astype(str))))
        filtro_bairro = st.multiselect("Filtrar por Bairro", options=lista_bairros)
    with c_filtro3:
        filtro_zona = st.multiselect("Filtrar por Zona", options=OPCOES_ZONA)
    with c_filtro4:
        filtro_status = st.multiselect("Filtrar por Status", options=OPCOES_STATUS)

    st.markdown("---")

    # Lógica de Filtragem
    df_display = df.copy()

    if filtro_texto:
        term = filtro_texto.lower()
        # Filtra se o termo está no ID externo OU na Rua
        df_display = df_display[
            df_display['external_id'].astype(str).str.lower().str.contains(term) | 
            df_display['rua'].astype(str).str.lower().str.contains(term)
        ]
    
    if filtro_bairro:
        df_display = df_display[df_display['bairro'].isin(filtro_bairro)]
        
    if filtro_zona:
        df_display = df_display[df_display['zona'].isin(filtro_zona)]
        
    if filtro_status:
        # Tratamento para status FALSE ou string vazia
        mask_status = df_display['status'].apply(lambda x: 'Pendente' if str(x).upper() == 'FALSE' else x)
        df_display = df_display[mask_status.isin(filtro_status)]

    st.caption(f"Exibindo {len(df_display)} registros de {len(df)} totais.")

    # --------------------------------------------------------
    # LÓGICA DE EDIÇÃO (Formulário aparece se clicou no lápis)
    # --------------------------------------------------------
    if 'edit_id' in st.session_state:
        st.info(f"✏️ Editando registro ID: {st.session_state.edit_id}")
        row_idx_list = df.index[df['id'] == st.session_state.edit_id].tolist()
        
        if row_idx_list:
            idx = row_idx_list[0]
            row_data = df.iloc[idx]
            with st.form("edit"):
                curr_st = row_data.get('status', 'Pendente')
                if str(curr_st).upper() == 'FALSE': curr_st = 'Pendente'
                idx_st = OPCOES_STATUS.index(curr_st) if curr_st in OPCOES_STATUS else 0
                
                c_edit1, c_edit2 = st.columns([1, 3])
                nst = c_edit1.selectbox("Novo Status", OPCOES_STATUS, index=idx_st)
                ndesc = c_edit2.text_area("Atualizar Relato/Descrição", value=row_data.get('descricao', ''), height=100)
                
                if st.form_submit_button("✅ Salvar Alterações"):
                    df.at[idx, 'status'] = nst
                    df.at[idx, 'descricao'] = ndesc
                    update_full_sheet(SHEET_DENUNCIAS, df)
                    st.success("Atualizado com sucesso!")
                    del st.session_state.edit_id
                    time.sleep(1)
                    st.rerun()
            
            if st.button("Cancelar Edição"):
                del st.session_state.edit_id
                st.rerun()
        st.markdown("---")

    # --------------------------------------------------------
    # LISTAGEM DOS CARDS
    # --------------------------------------------------------
    # Ordenar do mais recente para o mais antigo
    df_display = df_display.sort_values(by='id', ascending=False)

    for idx, row in df_display.iterrows():
        with st.container(border=True):
            # Ajustei as colunas para caber o botão de excluir (6 colunas agora)
            cols = st.columns([1, 3, 1.2, 0.5, 0.5, 0.5])
            
            # Col 1: ID e Data
            cols[0].markdown(f"**{row.get('external_id','')}**")
            cols[0].caption(row.get('created_at',''))
            
            # Col 2: Endereço e Descrição curta
            cols[1].write(f"📍 {row.get('rua','')} - {row.get('bairro','')}")
            desc_curta = str(row.get('descricao',''))[:60] + "..." if len(str(row.get('descricao',''))) > 60 else str(row.get('descricao',''))
            cols[1].caption(f"{row.get('tipo','')} | {desc_curta}")
            
            # Col 3: Status Colorido
            st_val = str(row.get('status',''))
            st_dsp = "Pendente" if st_val.upper() == 'FALSE' or st_val == '' else st_val
            clr = "orange" if st_dsp == "Pendente" else "green" if st_dsp == "Concluída" else "blue"
            cols[2].markdown(f":{clr}[**{st_dsp}**]")
            
            # Col 4: Botão PDF
            try:
                pdf_bytes = gerar_pdf(row)
                cols[3].download_button("📄", pdf_bytes, f"OS_{row.get('external_id','').replace('/','-')}.pdf", "application/pdf", key=f"pdf_{row['id']}")
            except:
                cols[3].error("Erro PDF")
            
            # Col 5: Botão Editar
            if cols[4].button("✏️", key=f"edt_{row['id']}", help="Editar Status/Descrição"):
                st.session_state.edit_id = row['id']
                st.rerun()

            # Col 6: Botão Excluir
            if cols[5].button("🗑️", key=f"del_{row['id']}", help="Excluir Permanentemente"):
                # Remove a linha onde o ID é igual ao ID do botão clicado
                df_novo = df[df['id'] != row['id']]
                update_full_sheet(SHEET_DENUNCIAS, df_novo)
                st.toast(f"Denúncia {row.get('external_id')} excluída!", icon="🗑️")
                time.sleep(1)
                st.rerun()

# ============================================================
# PÁGINA 4: REINCIDÊNCIAS
# ============================================================
elif page == "Reincidências":
    st.title("🔄 Reincidência")
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
                    if not desc_nova: st.error("Escreva algo.")
                    else:
                        agora_br = datetime.now(FUSO_BR).strftime('%Y-%m-%d %H:%M:%S')
                        timestamp = datetime.now(FUSO_BR).strftime('%d/%m/%Y %H:%M')
                        rec = {"external_id": real_id, "data_hora": agora_br, "origem": origem, "descricao": desc_nova, "registrado_por": user_info['name']}
                        salvar_dados_seguro(SHEET_REINCIDENCIAS, rec)
                        texto_add = f"\n\n{'='*20}\n[REINCIDÊNCIA - {timestamp}]\nFiscal: {user_info['name']} | Origem: {origem}\n{desc_nova}"
                        df_den.at[row_idx, 'descricao'] = str(desc_atual) + texto_add
                        df_den.at[row_idx, 'status'] = 'Pendente'
                        update_full_sheet(SHEET_DENUNCIAS, df_den)
                        st.success("Feito!")
                        time.sleep(2)
                        st.rerun()




