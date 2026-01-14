import streamlit as st
import pandas as pd
import hashlib
from datetime import datetime
import time
import pytz
import plotly

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

def gerar_pdf(dados):
    try:
        class PDF(FPDF):
            def header(self):
                try:
                    self.image('logo.png', x=90, y=8, w=30) 
                    self.ln(22)
                except:
                    self.ln(5)
                self.set_font('Arial', 'B', 14)
                self.cell(0, 6, clean_text("Autarquia de Urbanização e Meio Ambiente de Caruaru"), 0, 1, 'C')
                self.set_font('Arial', 'B', 12)
                self.cell(0, 6, clean_text("Central de Atendimento"), 0, 1, 'C')
                self.ln(5)
        
        def celula_cinza(texto):
            pdf.set_fill_color(220, 220, 220)
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(0, 6, clean_text(texto), 1, 1, 'L', fill=True)

        # --- INÍCIO DA GERAÇÃO DO PDF ---
        pdf = PDF()
        pdf.set_auto_page_break(auto=True, margin=25) 
        pdf.add_page()
        pdf.set_line_width(0.3)
        
        # Função auxiliar interna para células cinzas
        def celula_cinza(texto):
            pdf.set_fill_color(220, 220, 220)
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(0, 6, clean_text(texto), 1, 1, 'L', fill=True)

        # 1. TÍTULO DA SEÇÃO
        celula_cinza("ORDEM DE SERVIÇO - SETOR DE FISCALIZAÇÃO")
        
        # Tratamento de Data e Hora
        raw_date = str(dados.get('created_at', ''))
        data_fmt, hora_fmt = raw_date, ""
        try:
            dt_obj = pd.to_datetime(raw_date)
            data_fmt = dt_obj.strftime('%d/%m/%Y')
            hora_fmt = dt_obj.strftime('%H:%M')
        except:
            pass

        # Linha 1: Nº, DATA, HORA, ORIGEM
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(8, 8, "Nº", 1, 0, 'C')
        pdf.set_font("Arial", '', 9)
        pdf.cell(25, 8, clean_text(dados.get('external_id', '')), 1, 0, 'C')
        
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(12, 8, "DATA:", 1, 0, 'C')
        pdf.set_font("Arial", '', 9)
        pdf.cell(22, 8, data_fmt, 1, 0, 'C')

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(12, 8, "HORA:", 1, 0, 'C')
        pdf.set_font("Arial", '', 9)
        pdf.cell(15, 8, hora_fmt, 1, 0, 'C')

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(18, 8, "ORIGEM:", 1, 0, 'L')
        pdf.set_font("Arial", '', 8)
        pdf.cell(0, 8, clean_text(dados.get('origem', '')), 1, 1, 'L')

        # Linha 2: Bairro e Zona (TGS)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(35, 8, "BAIRRO OU DISTRITO:", 1, 0, 'L')
        pdf.set_font("Arial", '', 9)
        pdf.cell(120, 8, clean_text(dados.get('bairro', '')), 1, 0, 'L')
        
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(10, 8, "TGS:", 1, 0, 'C')
        pdf.set_font("Arial", '', 9)
        pdf.cell(0, 8, clean_text(dados.get('zona', '')), 1, 1, 'C')

        celula_cinza("DESCRIÇÃO DA ORDEM DE SERVIÇO")
        pdf.set_font("Arial", '', 9)
        pdf.multi_cell(0, 5, clean_text(dados.get('descricao', '')), 1, 'L')
        pdf.set_x(10)
        
        # 3. ENDEREÇO, GEOLOCALIZAÇÃO E PONTO DE REFERÊNCIA
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(30, 8, "LOGRADOURO:", "LTB", 0, 'L')
        pdf.set_font("Arial", '', 9)
        pdf.cell(0, 8, clean_text(dados.get('rua', '')), "RB", 1, 'L')
        
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(30, 8, "Nº:", "LB", 0, 'L')
        pdf.set_font("Arial", '', 9)
        pdf.cell(0, 8, clean_text(dados.get('numero', '')), "RB", 1, 'L')

       # --- CAMPO GEOLOCALIZAÇÃO E LINK MAPS ---
        lat = str(dados.get('latitude', ''))
        lon = str(dados.get('longitude', ''))
        link = str(dados.get('link_maps', '')) # Puxa o link do banco de dados
        
        geo_texto = f"Lat e Lon: {lat} , {lon}" if lat and lon else "Não informada"

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(35, 8, clean_text("GEOLOCALIZAÇÃO:"), 1, 0, 'L')
        pdf.set_font("Arial", '', 8)
        pdf.cell(0, 8, clean_text(geo_texto), 1, 1, 'L')

        if link:
            pdf.set_font("Arial", 'B', 8)
            pdf.cell(35, 8, "LINK MAPS:", 1, 0, 'L')
            pdf.set_font("Arial", '', 7)
            pdf.set_text_color(0, 0, 255) # Azul para parecer link
            pdf.cell(0, 8, clean_text(link), 1, 1, 'L', link=link)
            pdf.set_text_color(0, 0, 0) # Volta para preto

        # --- CAMPO PONTO DE REFERÊNCIA ---
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(35, 8, clean_text("PONTO DE REFERÊNCIA: "), 1, 0, 'L')
        pdf.set_font("Arial", '', 8)
        pdf.cell(0, 8, clean_text(dados.get('ponto_referencia', '')), 1, 1, 'L')

       # 4. ASSINATURAS
        pdf.ln(5)
        y_sig = pdf.get_y()
        if y_sig > 230: pdf.add_page(); y_sig = pdf.get_y()

        pdf.rect(10, y_sig, 130, 18) 
        pdf.rect(140, y_sig, 60, 18) 
        
        pdf.set_fill_color(220, 220, 220) 
        pdf.set_xy(140, y_sig)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(60, 6, "Rubrica", 1, 0, 'C', fill=True)

        pdf.set_xy(12, y_sig + 2)
        pdf.set_font("Arial", 'B', 7)
        pdf.cell(0, 4, "RECEBIDO POR:", 0, 1)
        
        # --- LINHA ADICIONADA PARA PUXAR O NOME ---
        pdf.set_x(12)
        pdf.set_font("Arial", '', 9)
        pdf.cell(125, 8, clean_text(dados.get('quem_recebeu', '')), 0, 0, 'L')
                
      # 5. INFORMAÇÕES DA FISCALIZAÇÃO
        pdf.set_xy(10, y_sig + 22)
        celula_cinza("INFORMAÇÕES DA FISCALIZAÇÃO")
        
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(90, 10, clean_text("DATA DA VISTORIA:            "), 1, 0, 'L')
        pdf.cell(0, 10, "HORA:             ", 1, 1, 'L')

        # Cabeçalho do quadro
        pdf.set_font("Arial", '', 7)
        pdf.cell(0, 5, clean_text("OBSERVAÇÕES E DESCRIÇÃO DA OCORRÊNCIA"), "LR", 1, 'C')
        
        # 1. Espaço superior do quadro (Altura total de 95mm - 30mm da rubrica = 65mm)
        pdf.cell(0, 75, "", "LR", 1, 'L') 

        # 2. Linha da Rubrica (posicionada a 3cm do fundo)
        pdf.set_font("Arial", 'B', 9)
        # "LR" mantém as bordas laterais abertas para continuar o quadro
        pdf.cell(0, 5, clean_text("  RUBRICA:                       "), "LR", 1, 'L')

        # 3. Espaço inferior final (os últimos 25mm para fechar o quadro)
        # "LRB" coloca a linha de baixo que fecha o quadro
        pdf.cell(0, 15, "", "LRB", 1, 'L') 

        pdf_output = pdf.output(dest='S')
        return bytes(pdf_output) if not isinstance(pdf_output, str) else pdf_output.encode('latin-1')


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
    st.title("📊 Visão Geral da Fiscalização")
    df = load_data(SHEET_DENUNCIAS)
    
    if not df.empty:
        # --- MÉTRICAS PRINCIPAIS ---
        df['status'] = df['status'].replace({'FALSE': 'Pendente', 'False': 'Pendente'})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de Denúncias", len(df))
        c2.metric("Pendentes", len(df[df['status'] == 'Pendente']))
        c3.metric("Em Andamento", len(df[df['status'] == 'Em Monitoramento']))
        c4.metric("Concluídas", len(df[df['status'] == 'Concluída']))

        st.divider()

        with col_graf1:
            st.subheader("Tipo de Denúncia")
    
    # 1. Padronização dos Nomes (Limpeza)
    df_tipo = df.copy()
    df_tipo['tipo'] = df_tipo['tipo'].replace({
        'Urbana': 'Urbano', 
        'urbano': 'Urbano',
        'urbana': 'Urbano'
    })

    # 2. Contagem
    contagem = df_tipo['tipo'].value_counts().reset_index()
    contagem.columns = ['Tipo', 'Qtd']

    # 3. Gráfico de Rosca (Donut)
    import plotly.express as px
    fig = px.pie(
        contagem, 
        values='Qtd', 
        names='Tipo', 
        hole=0.5, # Define o buraco no meio
        color_discrete_sequence=px.colors.qualitative.Safe
    )
    
    # Estética: Remove legenda se os nomes couberem no gráfico
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.update_layout(margin=dict(t=30, b=0, l=0, r=0), showlegend=False)
    
    st.plotly_chart(fig, use_container_width=True)

        # --- GRÁFICOS: LINHA 2 (RANKINGS) ---
    col_rank1, col_rank2 = st.columns(2)

        with col_rank1:
            st.subheader("🏆 Ranking por Bairro")
            # Top 10 Bairros
            df_bairro = df['bairro'].value_counts().nlargest(10).reset_index()
            df_bairro.columns = ['Bairro', 'Total']
            fig_bairro = px.bar(df_bairro, x='Total', y='Bairro', orientation='h',
                                 text='Total', color='Total', color_continuous_scale='Blues')
            fig_bairro.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_bairro, use_container_width=True)

        with col_rank2:
            st.subheader("📍 Denúncias por Zona")
            df_zona = df['zona'].value_counts().reset_index()
            df_zona.columns = ['Zona', 'Total']
            fig_zona = px.bar(df_zona, x='Zona', y='Total', color='Zona',
                               text_auto=True)
            st.plotly_chart(fig_zona, use_container_width=True)

        # --- TABELA RECENTE ---
        st.subheader("📅 Últimas Ocorrências")
        st.dataframe(df.tail(10)[['external_id', 'bairro', 'status', 'created_at']], use_container_width=True)

    else:
        st.info("Nenhuma denúncia encontrada para gerar estatísticas.")

# ============================================================
# ALTERAÇÃO 3: PÁGINA DE REGISTRO
# ============================================================
elif page == "Registrar Denúncia":
    st.title("📝 Nova Denúncia")
    
    # Inicializa o estado de trava
    if 'processando_registro' not in st.session_state:
        st.session_state.processando_registro = False

    with st.form('reg'):
        c1, c2 = st.columns(2)
        origem = c1.selectbox('Origem', OPCOES_ORIGEM)
        tipo = c2.selectbox('Tipo', OPCOES_TIPO)
        
        rua = st.text_input('Rua')
        c3, c4, c5 = st.columns(3)
        numero = c3.text_input('Número')
        bairro = c4.text_input('Bairro')
        zona = c5.selectbox('Zona', OPCOES_ZONA)
        
        st.markdown("---")
        st.markdown("**📍 Localização e Referência**")
        col_lat, col_lon = st.columns(2)
        latitude = col_lat.text_input('Latitude (Ex: -8.2828)')
        longitude = col_lon.text_input('Longitude (Ex: -35.9701)')
        ponto_ref = st.text_input('Ponto de Referência')

        # Lógica do Link: Aparece assim que os campos são preenchidos
        link_google = ""
        if latitude and longitude:
            link_google = f"https://www.google.com/maps?q={latitude},{longitude}"
            st.info(f"🔗 **Link Visualizado:** {link_google}")
        
        st.markdown("---")
        desc = st.text_area('Descrição da Ocorrência')
        quem = st.selectbox('Quem recebeu', OPCOES_FISCAIS_SELECT)
        
        # Botão com trava dinâmica
        btn_submit = st.form_submit_button(
            '💾 Salvar Denúncia', 
            disabled=st.session_state.processando_registro
        )
        
        if btn_submit:
            if not rua:
                st.error("O campo 'Rua' é obrigatório.")
            else:
                st.session_state.processando_registro = True
                with st.spinner('Gravando dados...'):
                    # 1. Carrega os dados mais recentes
                    df = load_data(SHEET_DENUNCIAS)
                    
                    # 2. Lógica Segura de ID: Pega o maior valor e soma 1
                    if not df.empty:
                        # Converte a coluna id para numérico caso venha como texto da planilha
                        ids_existentes = pd.to_numeric(df['id'], errors='coerce').dropna()
                        new_id = int(ids_existentes.max() + 1) if not ids_existentes.empty else 1
                    else:
                        new_id = 1
                    
                    # 3. Gera o ID Externo formatado (ex: 0041/2026)
                    ext_id = f"{new_id:04d}/{datetime.now().year}"
                    agora_br = datetime.now(FUSO_BR).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 4. Monta o registro
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
                        'latitude': latitude, 
                        'longitude': longitude,
                        'ponto_referencia': ponto_ref,
                        'link_maps': link_google,
                        'descricao': desc, 
                        'quem_recebeu': quem, 
                        'status': 'Pendente', 
                        'acao_noturna': 'FALSE'
                    }
                    
                    salvar_dados_seguro(SHEET_DENUNCIAS, record)
                    st.success(f"Denúncia {ext_id} salva!")
                    st.session_state.processando_registro = False
                    time.sleep(1)
                    st.rerun()

# ============================================================
# PÁGINA 3: HISTÓRICO / GERENCIAMENTO
# ============================================================
elif page == "Histórico / Editar":
    st.title("🗂️ Gerenciamento de Ocorrências")
    
    # 1. Carregar dados
    df = load_data(SHEET_DENUNCIAS)
    
    if df.empty:
        st.info("Nenhum registro encontrado.")
    else:
        # --- SEÇÃO DE FILTROS ---
        with st.expander("🔍 Filtros de Busca", expanded=False):
            c1, c2, c3, c4 = st.columns(4)
            f_bairro = c1.text_input("Bairro")
            f_zona = c2.selectbox("Zona", ["Todos"] + OPCOES_ZONA)
            f_status = c3.selectbox("Status", ["Todos"] + OPCOES_STATUS)
            f_id = c4.text_input("Nº da OS (Ex: 0001)")

        # Aplicar Filtros
        df_filtrado = df.copy()
        if f_bairro:
            df_filtrado = df_filtrado[df_filtrado['bairro'].str.contains(f_bairro, case=False, na=False)]
        if f_zona != "Todos":
            df_filtrado = df_filtrado[df_filtrado['zona'] == f_zona]
        if f_status != "Todos":
            df_filtrado = df_filtrado[df_filtrado['status'] == f_status]
        if f_id:
            df_filtrado = df_filtrado[df_filtrado['external_id'].str.contains(f_id, na=False)]

        # --- LÓGICA DE EDIÇÃO (APARECE NO TOPO SE CLICAR NO LÁPIS) ---
        if 'edit_id' in st.session_state:
            st.markdown("---")
            st.subheader(f"📝 Editando OS: {st.session_state.edit_id}")
            
            # Inicializa trava de edição
            if 'salvando_edicao' not in st.session_state:
                st.session_state.salvando_edicao = False

            idx_list = df.index[df['id'] == st.session_state.edit_id].tolist()
            if idx_list:
                idx = idx_list[0]
                row_data = df.iloc[idx]
                
                with st.form("form_edicao"):
                    col_e1, col_e2, col_e3 = st.columns(3)
                    def get_index(lista, valor):
                        return lista.index(valor) if valor in lista else 0

                    novo_status = col_e1.selectbox("Status", OPCOES_STATUS, index=get_index(OPCOES_STATUS, row_data['status']))
                    nova_zona = col_e2.selectbox("Zona", OPCOES_ZONA, index=get_index(OPCOES_ZONA, row_data['zona']))
                    nova_origem = col_e3.selectbox("Origem", OPCOES_ORIGEM, index=get_index(OPCOES_ORIGEM, row_data['origem']))
                    
                    col_e4, col_e5 = st.columns([2, 1])
                    nova_rua = col_e4.text_input("Rua", value=str(row_data.get('rua', '')))
                    nova_ref = col_e5.text_input("Ponto de Referência", value=str(row_data.get('ponto_referencia', '')))

                    col_lat, col_lon, col_num = st.columns(3)
                    nova_lat = col_lat.text_input("Latitude", value=str(row_data.get('latitude', '')))
                    nova_lon = col_lon.text_input("Longitude", value=str(row_data.get('longitude', '')))
                    novo_num = col_num.text_input("Número", value=str(row_data.get('numero', '')))
                    
                    nova_desc = st.text_area("Descrição", value=str(row_data.get('descricao', '')), height=150)
                    
                    # Link dinâmico na edição
                    link_edit = ""
                    if nova_lat and nova_lon:
                        link_edit = f"https://www.google.com/maps?q={nova_lat},{nova_lon}"
                        st.caption(f"Novo Link: {link_edit}")

                    c_btn1, c_btn2 = st.columns([1, 5])
                    # BOTÃO ATUALIZAR COM TRAVA
                    if c_btn1.form_submit_button("💾 Atualizar", disabled=st.session_state.salvando_edicao):
                        st.session_state.salvando_edicao = True
                        df.at[idx, 'status'] = novo_status
                        df.at[idx, 'zona'] = nova_zona
                        df.at[idx, 'origem'] = nova_origem
                        df.at[idx, 'rua'] = nova_rua
                        df.at[idx, 'numero'] = novo_num
                        df.at[idx, 'latitude'] = nova_lat
                        df.at[idx, 'longitude'] = nova_lon
                        df.at[idx, 'ponto_referencia'] = nova_ref
                        df.at[idx, 'descricao'] = nova_desc
                        df.at[idx, 'link_maps'] = link_edit
                        
                        update_full_sheet(SHEET_DENUNCIAS, df)
                        st.success("Atualizado com sucesso!")
                        st.session_state.salvando_edicao = False
                        del st.session_state.edit_id
                        time.sleep(1)
                        st.rerun()
                    
                    if c_btn2.form_submit_button("Cancelar"):
                        del st.session_state.edit_id
                        st.rerun()
            st.markdown("---")

        # --- LISTAGEM ÚNICA DE CARDS ---
        st.write(f"Exibindo **{len(df_filtrado)}** registros")
        df_filtrado = df_filtrado.sort_values(by='id', ascending=False)

        # O 'i' aqui garante que cada linha do loop tenha um número único
        for i, row in enumerate(df_filtrado.itertuples()):
            # Usamos row.id e row.external_id (itertuples é mais rápido e seguro)
            idx_real = row.id
            ext_id_limpo = str(row.external_id).replace('/', '_')

            with st.container(border=True):
                c_info, c_status, c_pdf, c_edit, c_del = st.columns([3, 1, 0.5, 0.5, 0.5])
                
                c_info.markdown(f"### OS {row.external_id}")
                c_info.write(f"📍 **{row.rua}**, {row.numero} - {row.bairro} ({row.zona})")
                c_info.caption(f"🗓️ {row.created_at} | 👤 {row.quem_recebeu}")
                
                st_val = str(row.status)
                clr = "orange" if st_val == "Pendente" else "green" if st_val == "Concluída" else "blue"
                c_status.markdown(f"<br>:{clr}[**{st_val.upper()}**]", unsafe_allow_html=True)
                
                # 1. BOTÃO PDF (CHAVE ÚNICA)
                res_pdf = gerar_pdf(row._asdict()) # converte linha para dicionário
                if isinstance(res_pdf, bytes):
                    c_pdf.markdown("<br>", unsafe_allow_html=True)
                    c_pdf.download_button(
                        "📄", 
                        res_pdf, 
                        f"OS_{ext_id_limpo}.pdf", 
                        "application/pdf", 
                        key=f"pdf_btn_{idx_real}_{i}"
                    )
                
                # 2. BOTÃO EDITAR (CHAVE ÚNICA)
                c_edit.markdown("<br>", unsafe_allow_html=True)
                if c_edit.button("✏️", key=f"ed_btn_{idx_real}_{i}"):
                    st.session_state.edit_id = idx_real
                    st.rerun()
                    
                # 3. BOTÃO DELETAR (CHAVE ÚNICA)
                c_del.markdown("<br>", unsafe_allow_html=True)
                if c_del.button("🗑️", key=f"del_btn_{idx_real}_{i}"):
                    st.session_state.confirm_del = idx_real

                # Confirmação de exclusão (CHAVE ÚNICA)
                if 'confirm_del' in st.session_state and st.session_state.confirm_del == idx_real:
                    st.error(f"Excluir permanentemente OS {row.external_id}?")
                    ca1, ca2 = st.columns([1, 8])
                    if ca1.button("Sim", key=f"conf_sim_{idx_real}_{i}"):
                        # ... lógica de exclusão ...
                        df_final = df[df['id'] != idx_real]
                        update_full_sheet(SHEET_DENUNCIAS, df_final)
                        del st.session_state.confirm_del
                        st.rerun()
                    if ca2.button("Não", key=f"conf_nao_{idx_real}_{i}"):
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
































































