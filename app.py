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
OPCOES_STATUS = ['Pendente', 'Em Monitoramento', 'Concluída', 'Arquivada']
OPCOES_ORIGEM = ['Pessoalmente', 'Telefone', 'Whatsapp', 'Ministério Publico', 'Administração', 'Ouvidoria', 'Disk Denuncia']
OPCOES_TIPO = ['Urbano', 'Ambiental', 'Urbana e Ambiental', 'Ação Noturna']
OPCOES_ZONA = ['NORTE', 'SUL', 'LESTE', 'OESTE', 'CENTRO', 'ZONA RURAL', '1° DISTRITO', '2° DISTRITO', 'DISTRITO INDUSTRIAL', '3° DISTRITO', '4° DISTRITO']
OPCOES_FISCAIS_SELECT = ['Edvaldo Wilson Bezerra da Silva - 000.323', 'PATRICIA MIRELLY BEZERRA CAMPOS - 000.332', 'Raiany Nayara de Lima - 000.362', 'Suellen Bezerra do Nascimeto - 000.417']

# SCHEMAS
DENUNCIA_SCHEMA = [
    'id', 'external_id', 'created_at', 'origem', 'tipo', 'rua', 
    'numero', 'bairro', 'zona', 'ponto_referencia', 'latitude', 'longitude', 'link maps', 
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
# FUNÇÃO DE SUPORTE (DEVE VIR ANTES DE GERAR_PDF)
# ============================================================
def clean_text(text):
    """Limpa o texto para evitar erros de codificação no PDF."""
    if text is None: 
        return ""
    # Converte para string e remove caracteres que o Latin-1 não suporta
    text = str(text).replace("–", "-").replace("“", '"').replace("”", '"').replace("’", "'")
    return text.encode('latin-1', 'replace').decode('latin-1')

from fpdf import FPDF
import pandas as pd

def clean_text(text):
    """Limpa o texto para evitar erros de codificação no PDF."""
    if text is None: 
        return ""
    text = str(text).replace("–", "-").replace("“", '"').replace("”", '"').replace("’", "'")
    return text.encode('latin-1', 'replace').decode('latin-1')

# ============================================================
# ALTERAÇÃO 2: ATUALIZAR A FUNÇÃO GERAR_PDF
# ============================================================

def gerar_pdf(dados):
    try:
        # ... (MANTENHA A CLASSE PDF E HEADER/FOOTER COMO JÁ ESTAVAM) ...
        class PDF(FPDF):
            def header(self):
                self.set_font('Arial', 'B', 14)
                self.cell(0, 6, clean_text("Autarquia de Urbanização e Meio Ambiente de Caruaru"), 0, 1, 'C')
                self.set_font('Arial', 'B', 12)
                self.cell(0, 6, clean_text("Central de Atendimento"), 0, 1, 'C')
                self.ln(5)
            
            def footer(self):
                self.set_y(-22)
                self.set_font('Arial', 'B', 9)
                self.set_fill_color(220, 220, 220)
                texto = (
                    "AUTARQUIA DE URBANIZAÇÃO E MEIO AMBIENTE DE CARUARU - URB\n"
                    "Rua Visconde de Inhaúma, 1191. Bairro Maurício de Nassau\n"
                    "Telefones: (81) 3101-0108   (81) 98384-3216"
                )
                self.multi_cell(0, 4, clean_text(texto), 1, 'C', fill=True)

        pdf = PDF()
        pdf.set_auto_page_break(auto=True, margin=25) 
        pdf.add_page()
        pdf.set_line_width(0.3)
        
        def celula_cinza(texto):
            pdf.set_fill_color(220, 220, 220)
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(0, 6, clean_text(texto), 1, 1, 'L', fill=True)

        # ... (MANTENHA A PARTE 1 E 2 DO CÓDIGO IGUAL: CABEÇALHO E DESCRIÇÃO) ...
        
        # --- REPETINDO O INÍCIO PARA CONTEXTO ---
        celula_cinza(f"ORDEM DE SERVIÇO - SETOR DE FISCALIZAÇÃO")
        # (Lógica de data/hora mantida...)
        raw_date = str(dados.get('created_at', ''))
        # ... (Código de Cabeçalho OS, Data, Origem, Bairro, Zona mantidos) ...
        
        # ... (Código da Descrição mantido) ...

        # -------------------------------------------------------------
        # AQUI COMEÇA A ALTERAÇÃO PRINCIPAL DO PDF
        # -------------------------------------------------------------
        
        # 3. Local e Geolocalização
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(30, 8, "LOGRADOURO:", "LTB", 0, 'L')
        pdf.set_font("Arial", '', 9)
        pdf.cell(0, 8, clean_text(dados.get('rua', '')), "RB", 1, 'L')
        
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(30, 8, "Nº:", "LB", 0, 'L')
        pdf.set_font("Arial", '', 9)
        pdf.cell(0, 8, clean_text(dados.get('numero', '')), "RB", 1, 'L')

        # Campo Geolocalização (Lat/Lon + Link se couber ou apenas Lat/Lon)
        celula_cinza("  ")
        lat = str(dados.get('latitude', ''))
        lon = str(dados.get('longitude', ''))
        link_maps = str(dados.get('link_maps', ''))
        
        # Monta o texto. Se tiver link, coloca o link, senão só lat/lon
        if lat and lon:
            geo_texto = f"Lat: {lat} | Lon: {lon}"
            # Se quiser imprimir o link no PDF descomente abaixo, mas links são longos e quebram o layout
            # if link_maps: geo_texto += f" - {link_maps}"
        else:
            geo_texto = "Não informada"

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(30, 8, "GEOLOCALIZAÇÃO: ", 1, 0, 'L')
        pdf.set_font("Arial", '', 7) # Fonte menor para caber
        pdf.cell(0, 8, geo_texto, 1, 1, 'L')

        # Campo Ponto de Referência (Preenchendo o espaço existente)
        ref_texto = str(dados.get('ponto_referencia', ''))
        
        pdf.set_font("Arial", 'B', 7)
        pdf.cell(35, 8, clean_text("PONTO DE REFERÊNCIA:   "), 1, 0, 'L')
        pdf.set_font("Arial", '', 8)
        # AQUI: Substituímos o "" vazio pela variável ref_texto
        pdf.cell(0, 8, clean_text(ref_texto), 1, 1, 'L') 

        # -------------------------------------------------------------
        # FIM DA ALTERAÇÃO PRINCIPAL - O RESTO SEGUE NORMAL
        # -------------------------------------------------------------

        # 4. Assinatura e Restante do código (Mantidos iguais)
        pdf.ln(2)
        y_sig = pdf.get_y()
        if y_sig > 230: 
             pdf.add_page()
             y_sig = pdf.get_y()

        pdf.rect(10, y_sig, 130, 18) 
        pdf.rect(140, y_sig, 60, 18) 
        
        pdf.set_fill_color(200, 220, 255)
        pdf.set_xy(140, y_sig)
        pdf.set_font("Arial", '', 7)
        pdf.cell(60, 4, "Rubrica", 1, 0, 'C', fill=True)

        pdf.set_xy(12, y_sig + 2)
        pdf.set_font("Arial", 'B', 7)
        pdf.cell(0, 4, "RECEBIDO POR:", 0, 1)
        pdf.set_font("Arial", '', 9)
        pdf.set_x(12)
        pdf.cell(125, 8, clean_text(dados.get('quem_recebeu', '')), 0, 0, 'L')

        pdf.set_xy(10, y_sig + 22)
        celula_cinza("INFORMAÇÕES DA FISCALIZAÇÃO")
        
        y_fisc = pdf.get_y()
        pdf.set_fill_color(200, 220, 255)
        pdf.set_xy(140, y_fisc - 6) 
        pdf.cell(60, 6, "Rubrica", 1, 1, 'C', fill=True)
        
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(90, 8, "DATA DA VISTORIA: _____/_____/_______", 1, 0, 'L')
        pdf.cell(0, 8, "HORA: _____:_____", 1, 1, 'L')

        pdf.set_font("Arial", '', 7)
        pdf.cell(0, 5, "OBSERVAÇÕES E DESCRIÇÃO DA OCORRÊNCIA", "LR", 1, 'C')
        pdf.cell(0, 45, "", "LRB", 1, 'L')

        pdf_output = pdf.output(dest='S')
        if isinstance(pdf_output, str):
            return pdf_output.encode('latin-1')
        return bytes(pdf_output)

    except Exception as e:
        return str(e)
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
# ALTERAÇÃO 3: PÁGINA DE REGISTRO
# ============================================================
elif page == "Registrar Denúncia":
    st.title("📝 Nova Denúncia")
    with st.form('reg'):
        c1, c2 = st.columns(2)
        origem = c1.selectbox('Origem', OPCOES_ORIGEM)
        tipo = c2.selectbox('Tipo', OPCOES_TIPO)
        
        # Endereço
        rua = st.text_input('Rua')
        c3, c4, c5 = st.columns(3)
        numero = c3.text_input('Número')
        bairro = c4.text_input('Bairro')
        zona = c5.selectbox('Zona', OPCOES_ZONA)
        
        # --- NOVO: Geolocalização e Referência ---
        st.markdown("---")
        st.markdown("**📍 Localização e Referência**")
        col_lat, col_lon = st.columns(2)
        latitude = col_lat.text_input('Latitude (Ex: -8.2828)')
        longitude = col_lon.text_input('Longitude (Ex: -35.9701)')
        
        ponto_ref = st.text_input('Ponto de Referência')
        
        # Lógica visual para mostrar o link gerado (apenas informativo na tela)
        link_google = ""
        if latitude and longitude:
            link_google = f"https://www.google.com/maps?q={latitude},{longitude}"
            st.caption(f"Link gerado: {link_google}")
        # ------------------------------------------

        st.markdown("---")
        desc = st.text_area('Descrição da Ocorrência')
        quem = st.selectbox('Quem recebeu', OPCOES_FISCAIS_SELECT)
        
        if st.form_submit_button('💾 Salvar'):
            if not rua:
                st.error("Rua obrigatória.")
            else:
                df = load_data(SHEET_DENUNCIAS)
                new_id = len(df) + 1
                ext_id = f"{new_id:04d}/{datetime.now().year}"
                agora_br = datetime.now(FUSO_BR).strftime('%Y-%m-%d %H:%M:%S')
                
                # Atualizando o dicionário com os novos campos
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
                    'latitude': latitude,      # Salva o input
                    'longitude': longitude,    # Salva o input
                    'ponto_referencia': ponto_ref, # Salva o input
                    'link_maps': link_google,  # Salva o link gerado
                    'descricao': desc, 
                    'quem_recebeu': quem, 
                    'status': 'Pendente',
                    'acao_noturna': 'FALSE'
                }
                
                salvar_dados_seguro(SHEET_DENUNCIAS, record)
                st.success(f"Denúncia {ext_id} salva com sucesso!")
                time.sleep(1)
                st.rerun()
# ============================================================
# PÁGINA 3: HISTÓRICO / GERENCIAMENTO (COM FILTROS E EXCLUSÃO)
# ============================================================
elif page == "Histórico / Editar":
    st.title("🗂️ Gerenciamento de Ocorrências")
    
    # Carregar dados atualizados
    df = load_data(SHEET_DENUNCIAS)
    
    if df.empty:
        st.warning("Nenhum registro encontrado no banco de dados.")
        st.stop()

    # --- SEÇÃO DE FILTROS ---
    with st.expander("🔍 Filtros de Busca", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        f_bairro = c1.text_input("Bairro")
        f_zona = c2.selectbox("Zona", ["Todos"] + OPCOES_ZONA)
        f_status = c3.selectbox("Status", ["Todos"] + OPCOES_STATUS)
        f_id = c4.text_input("Nº da OS (Ex: 0001)")

    # Aplicar Filtros no DataFrame
    df_filtrado = df.copy()
    if f_bairro:
        df_filtrado = df_filtrado[df_filtrado['bairro'].str.contains(f_bairro, case=False, na=False)]
    if f_zona != "Todos":
        df_filtrado = df_filtrado[df_filtrado['zona'] == f_zona]
    if f_status != "Todos":
        df_filtrado = df_filtrado[df_filtrado['status'] == f_status]
    if f_id:
        df_filtrado = df_filtrado[df_filtrado['external_id'].str.contains(f_id, na=False)]

    # --- LÓGICA DE EDIÇÃO (MODAL SIMULADO) ---
    if 'edit_id' in st.session_state:
        st.markdown("---")
        st.subheader(f"📝 Editando OS: {st.session_state.edit_id}")
        idx_list = df.index[df['id'] == st.session_state.edit_id].tolist()
        
        if idx_list:
            idx = idx_list[0]
            row_data = df.iloc[idx]
            
            with st.form("form_edicao"):
                col_e1, col_e2 = st.columns(2)
                novo_status = col_e1.selectbox("Alterar Status", OPCOES_STATUS, 
                                             index=OPCOES_STATUS.index(row_data['status']) if row_data['status'] in OPCOES_STATUS else 0)
                nova_zona = col_e2.selectbox("Alterar Zona", OPCOES_ZONA,
                                           index=OPCOES_ZONA.index(row_data['zona']) if row_data['zona'] in OPCOES_ZONA else 0)
                
                nova_rua = st.text_input("Rua", value=row_data.get('rua', ''))
                nova_desc = st.text_area("Descrição dos Fatos", value=row_data.get('descricao', ''), height=150)
                
                c_btn1, c_btn2 = st.columns([1, 5])
                if c_btn1.form_submit_button("💾 Atualizar"):
                    df.at[idx, 'status'] = novo_status
                    df.at[idx, 'zona'] = nova_zona
                    df.at[idx, 'rua'] = nova_rua
                    df.at[idx, 'descricao'] = nova_desc
                    
                    update_full_sheet(SHEET_DENUNCIAS, df)
                    st.success("Informações atualizadas com sucesso!")
                    del st.session_state.edit_id
                    time.sleep(1)
                    st.rerun()
                
                if c_btn2.form_submit_button("Cancelar"):
                    del st.session_state.edit_id
                    st.rerun()
        st.markdown("---")

    # --- LISTAGEM DE CARDS ---
    st.write(f"Exibindo **{len(df_filtrado)}** registros")
    
    # Ordenar por ID decrescente (mais recentes primeiro)
    df_filtrado = df_filtrado.sort_values(by='id', ascending=False)

    for _, row in df_filtrado.iterrows():
        with st.container(border=True):
            # Layout de colunas: Info | Status | Ações
            c_info, c_status, c_pdf, c_edit, c_del = st.columns([3, 1, 0.5, 0.5, 0.5])
            
            # Coluna Informações
            c_info.markdown(f"### OS {row['external_id']}")
            c_info.write(f"📍 **{row['rua']}**, {row['numero']} - {row['bairro']} ({row['zona']})")
            c_info.caption(f"🗓️ {row['created_at']} | 👤 {row['quem_recebeu']}")
            
            # Coluna Status com cor
            st_val = str(row['status'])
            clr = "orange" if st_val == "Pendente" else "green" if st_val == "Concluída" else "blue"
            c_status.markdown(f"<br>:{clr}[**{st_val.upper()}**]", unsafe_allow_html=True)
            
            # Coluna PDF
            res_pdf = gerar_pdf(row)
            if isinstance(res_pdf, bytes):
                c_pdf.markdown("<br>", unsafe_allow_html=True)
                c_pdf.download_button("📄", res_pdf, f"OS_{row['external_id']}.pdf", "application/pdf", key=f"pdf_{row['id']}")
            
            # Coluna Editar
            c_edit.markdown("<br>", unsafe_allow_html=True)
            if c_edit.button("✏️", key=f"ed_{row['id']}"):
                st.session_state.edit_id = row['id']
                st.rerun()
                
            # Coluna Excluir (com confirmação via popover ou session_state)
            c_del.markdown("<br>", unsafe_allow_html=True)
            if c_del.button("🗑️", key=f"del_{row['id']}", help="Excluir Permanentemente"):
                st.session_state.confirm_del = row['id']

            # Alerta de Confirmação de Exclusão
            if 'confirm_del' in st.session_state and st.session_state.confirm_del == row['id']:
                st.error(f"⚠️ Tem certeza que deseja excluir a OS {row['external_id']}?")
                ca1, ca2 = st.columns([1, 8])
                if ca1.button("Sim, Excluir", key=f"conf_{row['id']}"):
                    # Remove do DataFrame e atualiza a planilha
                    df_final = df[df['id'] != row['id']]
                    update_full_sheet(SHEET_DENUNCIAS, df_final)
                    st.success("Registro removido!")
                    del st.session_state.confirm_del
                    time.sleep(1)
                    st.rerun()
                if ca2.button("Não, Voltar", key=f"back_{row['id']}"):
                    del st.session_state.confirm_del
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






















