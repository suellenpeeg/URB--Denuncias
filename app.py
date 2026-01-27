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

st.write("SECRETS:", list(st.secrets.keys()))
st.stop()

# ============================================================
# CONFIGURAÇÃO INICIAL
# ============================================================
SPREADSHEET_ID = "1lb5GjBpqbbgm_gTHlITdF1MyrNPQWCedRHhZoafnUEM"
st.set_page_config(page_title="URB Fiscalização", layout="wide")
FUSO_BR = pytz.timezone('America/Recife')

# Nomes das abas
SHEET_DENUNCIAS = "denuncias_registro"
SHEET_REINCIDENCIAS = "reincidencias"
SHEET_USUARIOS = "usuarios"

# Opções de Seleção
OPCOES_STATUS = ['Pendente', 'Em Monitoramento', 'Concluída', 'Arquivada']
OPCOES_ORIGEM = ['Pessoalmente', 'Telefone', 'Whatsapp', 'Ministério Publico', 'Administração/Gerência', 'Ouvidoria', 'Disk Denuncia']
OPCOES_TIPO = ['Urbano', 'Ambiental', 'Urbana e Ambiental', 'Ação Noturna']
OPCOES_ZONA = ['NORTE', 'SUL', 'LESTE', 'OESTE', 'CENTRO', 'ZONA RURAL', '1° DISTRITO', '2° DISTRITO', 'DISTRITO INDUSTRIAL', '3° DISTRITO', '4° DISTRITO']
OPCOES_FISCAIS_SELECT = ['Edvaldo Wilson Bezerra da Silva - 000.323', 'PATRICIA MIRELLY BEZERRA CAMPOS - 000.332', 'Raiany Nayara de Lima - 000.362', 'Suellen Bezerra do Nascimeto - 000.417']

DENUNCIA_SCHEMA = [
    'id', 'external_id', 'created_at', 'origem', 'tipo', 'num_encaminhamento', 'rua', 
    'numero', 'bairro', 'zona', 'ponto_referencia', 'latitude', 'longitude', 'link_maps', 
    'descricao', 'observacoes', 'quem_recebeu', 'status', 'acao_noturna'
]

# ============================================================
# CONEXÃO GOOGLE SHEETS
# ============================================================
class SheetsClient:
    @staticmethod
    def get_client():
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )

        gc = gspread.authorize(creds)
        key = st.secrets["SPREADSHEET_KEY"]

        return gc, key

# ============================================================
# FUNÇÕES DE BANCO DE DADOS (PROTEÇÃO CONTRA APAGAMENTO)
# ============================================================
def update_full_sheet(sheet_name, df):
    gc, key = SheetsClient.get_client()
    sh = gc.open_by_key(key)

    try:
        ws = sh.worksheet(sheet_name)
    except WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=50)

    ws.clear()
    ws.update([df.columns.tolist()] + df.astype(str).values.tolist())

def gerar_ids_seguros():
    """Gera ID Único para o sistema e ID Sequencial para a prefeitura."""
    id_interno = str(uuid.uuid4())[:8]
    df = load_data(SHEET_DENUNCIAS)
    ano_atual = datetime.now().year
    if df.empty or 'external_id' not in df.columns:
        proximo_num = 1
    else:
        try:
            nums = df['external_id'].str.split('/').str[0].astype(int)
            proximo_num = nums.max() + 1
        except:
            proximo_num = len(df) + 1
    return id_interno, f"{proximo_num:04d}/{ano_atual}"

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

        origem = dados.get('origem', '')
        num_encaminhamento = dados.get('num_encaminhamento', '')

        if origem in ["Ouvidoria", "Ministério Publico", "Disk Denuncia"] and num_encaminhamento:
           origem_texto = f"{origem} - Nº {num_encaminhamento}"
        else:
           origem_texto = origem

        pdf.set_font("Arial", 'B', 8)
        pdf.cell(18, 8, "ORIGEM:", 1, 0, 'L')
        pdf.set_font("Arial", '', 8)
        pdf.cell(0, 8, clean_text(origem_texto), 1, 1, 'L')

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

        obs_texto = dados.get('observacoes', '').strip()

        pdf.ln(5)

        celula_cinza("OBSERVAÇÕES ADMINISTRATIVAS / DE CAMPO")

        pdf.set_font("Arial", '', 9)

        if obs_texto:
           pdf.multi_cell(0,6,clean_text(obs_texto),1,'L')
        else:
        # Mantém espaço em branco quando ainda não houver observações
           pdf.cell(0, 30, "", 1, 1, 'L')

        pdf_output = pdf.output(dest='S')
        return bytes(pdf_output) if not isinstance(pdf_output, str) else pdf_output.encode('latin-1')


    except Exception as e:
        return str(e)
# ============================================================
# FUNÇÕES DE BANCO DE DADOS (BLINDADAS)
# ============================================================

def get_worksheet(sheet_name):
    gc, key = SheetsClient.get_client()
    sh = gc.open_by_key(key)

    try:
        ws = sh.worksheet(sheet_name)
    except WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=50)

        if sheet_name == SHEET_DENUNCIAS:
            ws.append_row(DENUNCIA_SCHEMA)
        elif sheet_name == SHEET_USUARIOS:
            ws.append_row(["username", "password", "name", "role"])
        elif sheet_name == SHEET_REINCIDENCIAS:
            ws.append_row(REINCIDENCIA_SCHEMA)

    return ws


def load_data(sheet_name):
    ws = get_worksheet(sheet_name)
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    return df.fillna("")


def salvar_dados_seguro(sheet_name, row_dict):
    ws = get_worksheet(sheet_name)
    headers = ws.row_values(1)

    if not headers:
        if sheet_name == SHEET_DENUNCIAS:
            headers = DENUNCIA_SCHEMA
        elif sheet_name == SHEET_REINCIDENCIAS:
            headers = REINCIDENCIA_SCHEMA
        ws.append_row(headers)

    values = [str(row_dict.get(h, "")) for h in headers]
    ws.append_row(values)


def update_full_sheet(sheet_name, df):
    try:
        ws = get_worksheet(sheet_name)

        # Garante DataFrame seguro
        if df.empty and sheet_name == SHEET_DENUNCIAS:
            df_clean = pd.DataFrame(columns=DENUNCIA_SCHEMA)
        else:
            df_clean = df.fillna("").astype(str)

        dados = [df_clean.columns.tolist()] + df_clean.values.tolist()

        # Atualiza tudo de uma vez (SEM clear)
        ws.update("A1", dados)

    except Exception as e:
        st.error(f"Erro crítico ao salvar no Banco de Dados: {e}")
        raise  # importante para log


def gerar_novo_id():
    ws = get_worksheet("config")

    if not ws.row_values(1):
        ws.append_row(["ultimo_id"])
        ws.append_row([0])

    valor_atual = ws.acell("A2").value
    ultimo_id = int(valor_atual) if valor_atual else 0

    novo_id = ultimo_id + 1
    ws.update("A2", [[novo_id]])

    return novo_id

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

    # --- SANITIZAÇÃO DO ID (OBRIGATÓRIA) ---
    if 'id' in df.columns:
        df['id'] = pd.to_numeric(df['id'], errors='coerce')
        df = df.dropna(subset=['id'])
        df['id'] = df['id'].astype(int)
        df = df.drop_duplicates(subset=['id'], keep='last')

    
    if not df.empty:
        # --- MÉTRICAS PRINCIPAIS ---
        df['status'] = df['status'].replace({'FALSE': 'Pendente', 'False': 'Pendente'})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de Denúncias", len(df))
        c2.metric("Pendentes", len(df[df['status'] == 'Pendente']))
        c3.metric("Em Andamento", len(df[df['status'] == 'Em Monitoramento']))
        c4.metric("Concluídas", len(df[df['status'] == 'Concluída']))

        st.divider()

        # --- GRÁFICOS: LINHA 1 (TIPO E FONTE) ---
        col_graf1, col_graf2 = st.columns(2) # Define as colunas aqui

        with col_graf1:
            st.subheader("Tipo de Denúncia")
            
            # 1. Padronização dos Nomes (Limpeza) dentro do bloco identado
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
                hole=0.5,
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(margin=dict(t=30, b=0, l=0, r=0), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with col_graf2:
            st.subheader("Fonte da Denúncia")
            df_origem = df['origem'].value_counts().reset_index()
            df_origem.columns = ['Fonte', 'Total']
            fig_origem = px.bar(df_origem, x='Total', y='Fonte', orientation='h', text_auto=True)
            fig_origem.update_layout(margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig_origem, use_container_width=True)

        st.divider()

        # --- GRÁFICOS: LINHA 2 (RANKINGS) ---
        col_rank1, col_rank2 = st.columns(2)

        with col_rank1:
            st.subheader("🏆 Ranking por Bairro")
            df_bairro = df['bairro'].value_counts().nlargest(10).reset_index()
            df_bairro.columns = ['Bairro', 'Total']
            fig_bairro = px.bar(df_bairro, x='Total', y='Bairro', orientation='h',
                               text='Total', color='Total', color_continuous_scale='Blues')
            fig_bairro.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
            st.plotly_chart(fig_bairro, use_container_width=True)

        with col_rank2:
            st.subheader("📍 Denúncias por Zona")
            df_zona = df['zona'].value_counts().reset_index()
            df_zona.columns = ['Zona', 'Total']
            fig_zona = px.bar(df_zona, x='Zona', y='Total', color='Zona', text_auto=True)
            fig_zona.update_layout(showlegend=False)
            st.plotly_chart(fig_zona, use_container_width=True)

        st.divider()

        # --- TABELA RECENTE ---
        st.subheader("📅 Últimas Ocorrências")
        st.dataframe(df.tail(10)[['external_id', 'bairro', 'status', 'created_at']], use_container_width=True)

    else:
        st.info("Nenhuma denúncia encontrada para gerar estatísticas.")
# ============================================================
elif page == "Registrar Denúncia":
    st.title("📝 Nova Denúncia")

    ORIGENS_EXTERNAS = ["Ouvidoria", "Ministério Publico", "Disk Denuncia"]

    # ---------------- CONTROLE FORA DO FORM ----------------
    c1, c2 = st.columns(2)
    origem = c1.selectbox("Origem", OPCOES_ORIGEM)
    tipo = c2.selectbox("Tipo", OPCOES_TIPO)

    num_encaminhamento = ""
    if origem in ORIGENS_EXTERNAS:
        st.info(f"Preencha o número do protocolo vindo do(a) {origem}")
        num_encaminhamento = st.text_input(
            "Nº do Encaminhamento / Protocolo"
        )

    # ---------------- FORM PRINCIPAL ----------------
    with st.form("form_denuncia"):

        rua = st.text_input("Rua")
        c3, c4, c5 = st.columns(3)
        numero = c3.text_input("Número")
        bairro = c4.text_input("Bairro")
        zona = c5.selectbox("Zona", OPCOES_ZONA)

        st.markdown("---")
        col_lat, col_lon = st.columns(2)
        latitude = col_lat.text_input("Latitude")
        longitude = col_lon.text_input("Longitude")
        ponto_ref = st.text_input("Ponto de Referência")

        link_google = ""
        if latitude and longitude:
            link_google = f"https://www.google.com/maps?q={latitude},{longitude}"
            st.caption(link_google)

        st.markdown("---")
        desc = st.text_area("Descrição da Ocorrência")
        quem = st.selectbox("Quem recebeu", OPCOES_FISCAIS_SELECT)

        btn_submit = st.form_submit_button("💾 Salvar Denúncia")

    if btn_submit:
        if not rua:
            st.error("O campo Rua é obrigatório.")
        elif origem in ORIGENS_EXTERNAS and not num_encaminhamento:
            st.error(f"Para {origem}, é obrigatório informar o Nº do Encaminhamento.")
        else:
            new_id = gerar_novo_id()
            ext_id = f"{new_id:04d}/{datetime.now().year}"
            agora_br = datetime.now(FUSO_BR).strftime("%Y-%m-%d %H:%M:%S")

            record = {
                "id": new_id,
                "external_id": ext_id,
                "created_at": agora_br,
                "origem": origem,
                "tipo": tipo,
                "num_encaminhamento": num_encaminhamento,
                "rua": rua,
                "numero": numero,
                "bairro": bairro,
                "zona": zona,
                "latitude": latitude,
                "longitude": longitude,
                "ponto_referencia": ponto_ref,
                "link_maps": link_google,
                "descricao": desc,
                "observacoes": "",
                "quem_recebeu": quem,
                "status": "Pendente",
                "acao_noturna": "FALSE"
            }

            salvar_dados_seguro(SHEET_DENUNCIAS, record)
            st.success(f"Denúncia {ext_id} salva!")
            time.sleep(1)
            st.rerun()

# ============================================================
# PÁGINA 3: HISTÓRICO / GERENCIAMENTO (BLINDADO)
# ============================================================
elif page == "Histórico / Editar":
    st.title("🗂️ Gerenciamento de Ocorrências")

    df = load_data(SHEET_DENUNCIAS)
    df_filtrado = df.copy()

    if df.empty:
        st.info("Nenhum registro encontrado.")
    else:
        # ===============================
        # FILTROS
        # ===============================
        with st.expander("🔍 Filtros de Busca", expanded=False):
            c0, c1, c2, c3, c4 = st.columns([2, 1, 1, 1, 1])

            f_busca = c0.text_input(
                "🔎 Busca geral",
                placeholder="Pesquisar em qualquer campo...",
                key="filtro_busca_geral"
            )
            f_bairro = c1.text_input("Bairro", key="filtro_bairro")
            f_zona = c2.selectbox("Zona", ["Todos"] + OPCOES_ZONA, key="filtro_zona")
            f_status = c3.selectbox("Status", ["Todos"] + OPCOES_STATUS, key="filtro_status")
            f_id = c4.text_input("Nº da OS", key="filtro_id")

        # ===============================
        # APLICAR FILTROS
        # ===============================
        df_filtrado = df.copy()

        if f_bairro:
            df_filtrado = df_filtrado[
                df_filtrado['bairro'].astype(str).str.contains(f_bairro, case=False, na=False)
            ]

        if f_zona != "Todos":
            df_filtrado = df_filtrado[df_filtrado['zona'] == f_zona]

        if f_status != "Todos":
            df_filtrado = df_filtrado[df_filtrado['status'] == f_status]

        if f_id:
            df_filtrado = df_filtrado[
                df_filtrado['external_id'].astype(str).str.contains(f_id, na=False)
            ]

        if f_busca:
            termo = f_busca.strip()
            colunas_busca = [
                'descricao',
                'observacoes',
                'bairro',
                'rua',
                'origem',
                'external_id'
            ]

            mask = None
            for col in colunas_busca:
                if col in df_filtrado.columns:
                    m = df_filtrado[col].astype(str).str.contains(termo, case=False, na=False)
                    mask = m if mask is None else (mask | m)

            if mask is not None:
                df_filtrado = df_filtrado[mask]

        # ====================================================
        # EDIÇÃO (SÓ APARECE SE CLICAR NO ✏️)
        # ====================================================
        if 'edit_id' in st.session_state:
            st.markdown("---")
            st.subheader(f"📝 Editando OS: {st.session_state.edit_id}")

            idx_list = df.index[df['id'] == st.session_state.edit_id].tolist()
            if idx_list:
                idx = idx_list[0]
                row = df.loc[idx]

                with st.form("form_edicao_os"):
                    st.markdown("### 🗒️ Observações Administrativas / de Campo")

                    nova_obs = st.text_area(
                        "Uso interno da fiscalização",
                        value=str(row.get('observacoes', '')),
                        height=150
                    )

                    st.markdown("---")
                    c1, c2, c3 = st.columns(3)

                    def idx_op(lista, val):
                        return lista.index(val) if val in lista else 0

                    novo_status = c1.selectbox(
                        "Status", OPCOES_STATUS,
                        index=idx_op(OPCOES_STATUS, row['status'])
                    )
                    nova_zona = c2.selectbox(
                        "Zona", OPCOES_ZONA,
                        index=idx_op(OPCOES_ZONA, row['zona'])
                    )
                    nova_origem = c3.selectbox(
                        "Origem", OPCOES_ORIGEM,
                        index=idx_op(OPCOES_ORIGEM, row['origem'])
                    )

                    c4, c5 = st.columns([2, 1])
                    nova_rua = c4.text_input("Rua", value=str(row.get('rua', '')))
                    novo_num = c5.text_input("Número", value=str(row.get('numero', '')))

                    nova_desc = st.text_area(
                        "Descrição",
                        value=str(row.get('descricao', '')),
                        height=120
                    )

                    b1, b2 = st.columns([1, 4])

                    if b1.form_submit_button("💾 Atualizar"):
                        df.at[idx, 'observacoes'] = nova_obs
                        df.at[idx, 'status'] = novo_status
                        df.at[idx, 'zona'] = nova_zona
                        df.at[idx, 'origem'] = nova_origem
                        df.at[idx, 'rua'] = nova_rua
                        df.at[idx, 'numero'] = novo_num
                        df.at[idx, 'descricao'] = nova_desc

                        update_full_sheet(SHEET_DENUNCIAS, df)
                        st.success("Atualizado com sucesso!")
                        del st.session_state.edit_id
                        time.sleep(1)
                        st.rerun()

                    if b2.form_submit_button("Cancelar"):
                        del st.session_state.edit_id
                        st.rerun()

        # ====================================================
        # LISTAGEM (SEMPRE APARECE)
        # ====================================================
        for i, row in df_filtrado.sort_values(by='id', ascending=False).iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1, 3, 1.5, 1])

                c1.markdown(f"**{row['external_id']}**\n\n{row['created_at'][:10]}")

                c2.markdown(
                    f"📍 **{row['bairro']}** - {row['rua']}, {row['numero']}\n\n"
                    f"📝 _{row['descricao'][:100]}..._"
                )

                cor = (
                    "orange" if row['status'] == "Pendente"
                    else "blue" if "Monitoramento" in row['status']
                    else "green" if row['status'] == "Concluída"
                    else "gray"
                )
                c3.markdown(f":{cor}[**{row['status']}**]")

                b1, b2, b3, b4 = c4.columns(4)

                if b1.button("👁️", key=f"view_{row['id']}_{i}"):
                    st.session_state.view_id = row['id']

                if b2.button("✏️", key=f"edit_{row['id']}_{i}"):
                    st.session_state.edit_id = row['id']
                    st.rerun()

                pdf_b = gerar_pdf(row)
                b3.download_button(
                    "📄",
                    pdf_b,
                    f"OS_{row['id']}.pdf",
                    "application/pdf",
                    key=f"pdf_{row['id']}_{i}"
                )

                if b4.button("🗑️", key=f"del_{row['id']}_{i}"):
                    if user_info['role'] == 'admin':
                        df = df[df['id'] != row['id']]
                        update_full_sheet(SHEET_DENUNCIAS, df)
                        st.toast("Registro excluído com sucesso!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Apenas administradores podem excluir registros.")

                # 🔎 VISUALIZAÇÃO COMPLETA
                if st.session_state.get("view_id") == row["id"]:
                    with st.expander("📋 Detalhes completos", expanded=True):
                        st.markdown(f"""
**Origem:** {row['origem']}  
**Zona:** {row['zona']}  
**Endereço:** {row['rua']}, {row['numero']} – {row['bairro']}

**Descrição:**  
{row['descricao']}
""")

                        obs = row.get("observacoes", "")
                        if obs and str(obs).strip():
                            st.markdown("---")
                            st.markdown("### 🗒️ Observações Administrativas / de Campo")
                            st.markdown(obs)



# ============================================================
# PÁGINA: REINCIDÊNCIAS
# ============================================================
if page == "Reincidências":
    st.title("🔄 Reincidência")

    df_den = load_data(SHEET_DENUNCIAS)

    if df_den.empty:
        st.info("Nenhuma denúncia cadastrada.")
    else:
        df_den['label'] = (
            df_den['external_id'].astype(str)
            + " - "
            + df_den['rua'].astype(str)
        )

        escolha = st.selectbox(
            "Denúncia Original",
            df_den['label'].tolist()
        )

        if escolha:
            real_id = escolha.split(" - ")[0]
            row_idx = df_den.index[
                df_den['external_id'] == real_id
            ].tolist()[0]

            desc_atual = df_den.at[row_idx, 'descricao']

            with st.expander("📄 Descrição atual"):
                st.text(desc_atual)

            with st.form("form_reincidencia"):
                desc_nova = st.text_area(
                    "Novo Relato da Reincidência",
                    height=150
                )
                origem = st.selectbox("Origem", OPCOES_ORIGEM)

                if st.form_submit_button("💾 Salvar Reincidência"):
                    if not desc_nova:
                        st.error("O relato não pode ficar vazio.")
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

                        texto_add = (
                            f"\n\n{'='*30}\n"
                            f"[REINCIDÊNCIA - {timestamp}]\n"
                            f"Fiscal: {user_info['name']} | Origem: {origem}\n"
                            f"{desc_nova}"
                        )

                        df_den.at[row_idx, 'descricao'] = (
                            str(desc_atual) + texto_add
                        )
                        df_den.at[row_idx, 'status'] = 'Pendente'

                        update_full_sheet(SHEET_DENUNCIAS, df_den)

                        st.success("Reincidência registrada com sucesso!")
                        time.sleep(1)
                        st.rerun()
























