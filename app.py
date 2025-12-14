import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import hashlib
from io import BytesIO
from PIL import Image 

# Import Google Sheets
import gspread
from google.oauth2 import service_account
from gspread.exceptions import WorksheetNotFound, SpreadsheetNotFound

# Import FPDF (Geração de PDF estável)
from fpdf import FPDF 

# --- Configuração da Página ---
st.set_page_config(page_title="URB Fiscalização - Denúncias", layout="wide")

# === DEBUG SECRETS ===
st.write("🔍 DEBUG: Chaves disponíveis em st.secrets:", list(st.secrets.keys()))

if "gcp_service_account" in st.secrets:
    st.write("🔍 DEBUG: Campos dentro de gcp_service_account:", list(st.secrets["gcp_service_account"].keys()))

    pk = st.secrets["gcp_service_account"].get("private_key", "")
    st.write("🔍 DEBUG: Tamanho da private_key:", len(pk))
    st.write("🔍 DEBUG: private_key começa com BEGIN?:", "BEGIN" in pk)
else:
    st.write("❌ Bloco gcp_service_account não encontrado!")

# --- Constantes e Caminhos ---
USERS_PATH = "users.json"
UPLOADS_DIR = "uploads" 
SHEET_NAME = "denuncias_registro" 

# --- Acesso Global à URL (Fora do Cache) ---
# Tenta o acesso aninhado, que é a forma mais provável de estar no seu Secrets
try:
    # Acessa a URL da planilha ANINHADA dentro do bloco [gcp_service_account]
    SPREADSHEET_URL = st.secrets["gcp_service_account"]["spreadsheet_url"]
except KeyError:
    try:
        # Fallback para o caso de a URL estar na raiz (menos provável)
        SPREADSHEET_URL = st.secrets["spreadsheet_url"]
    except KeyError:
        # Se nenhuma das opções funcionar, paramos a execução
        st.error("Erro: A chave 'spreadsheet_url' não foi encontrada. Verifique se está no painel de Secrets.")
        st.stop()


# --- Listas de Opções Globais (Mantidas) ---
OPCOES_BAIRROS = [
    "AGAMENON MAGALHÃES","ALTO DO MOURA","CAIUCÁ","CEDRO","CENTENÁRIO","CIDADE ALTA","CIDADE JARDIM",
    "DEPUTADO JOSÉ ANTÔNIO LIBERATO","DISTRITO INDUSTRIAL","DIVINÓPOLIS","INDIANÓPOLIS","JARDIM BOA VISTA",
    "JARDIM PANORAMA","JOÃO MOTA","JOSÉ CARLOS DE OLIVEIRA","KENNEDY","LUIZ GONZAGA","MANOEL BEZERRA LOPES",
    "MARIA AUXILIADORA","MAURÍCIO DE NASSAU","MORRO BOM JESUS","NINA LIBERATO","NOSSA SENHORA DAS DORES",
    "NOSSA SENHORA DAS GRAÇAS","NOVA CARUARU","PETRÓPOLIS","PINHEIRÓPOLIS","RENDEIRAS","RIACHÃO","SALGADO",
    "SANTA CLARA","SANTA ROSA","SÃO FRANCISCO","SÃO JOÃO DA ESCÓCIA","SÃO JOSÉ","SERRAS DO VALE",
    "SEVERINO AFONSO","UNIVERSITÁRIO","VASSOURAL","VILA PADRE INÁCIO","VERDE","VILA ANDORINHA","XIQUE-XIQUE"
]

OPCOES_ORIGEM = ['Pessoalmente','Telefone','Whatsapp','Ministério Publico','Administração','Ouvidoria','Disk Denuncia']
OPCOES_TIPO = ['Urbana','Ambiental','Urbana e Ambiental']
OPCOES_ZONA = ['NORTE','SUL','LESTE','OESTE','CENTRO','1° DISTRITO','2° DISTRITO','3° DISTRITO','4° DISTRITO','Zona rural']
OPCOES_FISCAIS = ['EDVALDO WILSON BEZERRA DA SILVA - 000.323','PATRICIA MIRELLY BEZERRA CAMPOS - 000.332','RAIANY NAYARA DE LIMA - 000.362','SUELLEN BEZERRA DO NASCIMENTO - 000.417']
OPCOES_STATUS = ['Pendente', 'Em Andamento', 'Concluída', 'Arquivada'] 

if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR, exist_ok=True)

# ---------------------- Google Sheets Connection (Singleton) ----------------------

# ---------------------- Google Sheets Connection (Singleton) ----------------------

class SheetsClient:
   from google.oauth2 import service_account

class SheetsClient:
    """Gerencia o cliente gspread, substituindo o @st.cache_resource."""
    _gc = None

    @classmethod
    def get_client(cls):
        if cls._gc is None:
            try:
                secrets = st.secrets["gcp_service_account"]

                private_key = secrets["private_key"].replace("\\n", "\n")

                info = {
                    "type": secrets["type"],
                    "project_id": secrets["project_id"],
                    "private_key_id": secrets["private_key_id"],
                    "private_key": private_key,
                    "client_email": secrets["streamlit-fiscalizacao@nice-dispatcher-481000-h9.iam.gserviceaccount.com"],
                    "client_id": secrets["client_id"],
                    "auth_uri": secrets["auth_uri"],
                    "token_uri": secrets["token_uri"],
                    "auth_provider_x509_cert_url": secrets["auth_provider_x509_cert_url"],
                    "client_x509_cert_url": secrets["client_x509_cert_url"],
                    "universe_domain": secrets["universe_domain"],
                }

                SCOPES = [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ]

                credentials = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=SCOPES,
                )

                cls._gc = gspread.authorize(credentials)

            except KeyError as e:
                st.error(f"Erro de Secrets: Falta a chave {e} no bloco [gcp_service_account].")
                return None

            except Exception as e:
                st.error("Erro fatal na autenticação com Google Sheets")
                st.code(repr(e))
                return None

        return cls._gc


# ---------------------- Funções de Manipulação de Dados (Adaptadas) ----------------------

@st.cache_data(ttl=60) # Caching para leitura frequente dos dados
def load_data_from_sheet(sheet_name): # REMOVIDO gc do argumento
    """Carrega todos os dados de uma aba da planilha."""
    
    # Obtém o cliente Singleton (não haseável)
    gc = SheetsClient.get_client()
    required_cols = ['id', 'external_id', 'created_at', 'origem', 'tipo', 'rua', 'numero', 'bairro', 'zona', 'latitude', 'longitude', 'descricao', 'fotos', 'quem_recebeu', 'status', 'acao_noturna', 'reincidencias']

    if not gc:
        return pd.DataFrame(columns=required_cols) 

    try:
        sh = gc.open_by_url(SPREADSHEET_URL) # Usa a URL global
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Adiciona colunas se faltarem para garantir a estrutura
        for col in required_cols:
            if col not in df.columns:
                df[col] = ''
        
        # Processamento de colunas JSON
        def safe_json_load(x):
            try:
                return json.loads(x) if x and isinstance(x, str) and x.strip().startswith(('{','[')) else []
            except:
                return []
                
        df['fotos'] = df['fotos'].apply(safe_json_load)
        df['reincidencias'] = df['reincidencias'].apply(safe_json_load)
        
        return df
        
    except SpreadsheetNotFound:
        st.error("Planilha não encontrada. Verifique a URL e se o Service Account tem acesso.")
        return pd.DataFrame(columns=required_cols)
        
    except WorksheetNotFound:
        st.warning(f"Aba '{sheet_name}' não encontrada. Criando nova aba...")
        try:
             sh.add_worksheet(title=sheet_name, rows=100, cols=20)
             sh.worksheet(sheet_name).append_row(required_cols)
             return pd.DataFrame(columns=required_cols)
        except Exception as e:
            st.error(f"Não foi possível criar a aba '{sheet_name}': {e}")
            return pd.DataFrame(columns=required_cols)
            
    except Exception as e:
       st.error("Erro ao carregar dados do Google Sheets:")
       st.code(repr(e))
       raise e


@st.cache_data(ttl=60) # Mantido o cache
def fetch_all_denuncias_df():
    """Função wrapper para carregar o DataFrame (com caching)."""
    # Chama a função de leitura que agora obtém o cliente internamente
    return load_data_from_sheet(SHEET_NAME)


def update_data_in_sheet(sheet_name, df): # REMOVIDO gc do argumento
    """Atualiza o Google Sheets com o DataFrame modificado."""
    gc = SheetsClient.get_client() # Obtém o cliente Singleton
    if not gc:
        st.error("Falha na conexão GSpread para escrita.")
        return 

    try:
        sh = gc.open_by_url(SPREADSHEET_URL) # Usa a URL global
        worksheet = sh.worksheet(sheet_name)
        
        # Converte as colunas de listas de volta para strings JSON
        df['fotos'] = df['fotos'].apply(lambda x: json.dumps(x) if isinstance(x, list) else '[]')
        df['reincidencias'] = df['reincidencias'].apply(lambda x: json.dumps(x) if isinstance(x, list) else '[]')
        
        # O gspread atualiza a partir da célula A1.
        data_to_write = [df.columns.tolist()] + df.values.tolist()
        worksheet.update('A1', data_to_write)
        
        # Invalidar o cache após a escrita para forçar a recarga
        load_data_from_sheet.clear()
        
    except Exception as e:
        st.error("Erro ao carregar dados do Google Sheets:")
        st.code(repr(e))
        raise e


def generate_external_id(df):
    """Gera ID baseado no último ID sequencial (MAX ID)."""
    # Garante que 'id' seja numérico para o max() funcionar
    max_id = pd.to_numeric(df['id'], errors='coerce').max() if not df.empty else 0
    next_id = int(max_id) + 1
    year = datetime.now().year
    return f"{next_id:04d}/{year}", next_id 

def insert_denuncia(record):
    """Adiciona um novo registro no Sheets."""
    df = fetch_all_denuncias_df()
    
    # 1. Definir ID Sequencial e External ID
    external_id, seq_id = generate_external_id(df)
    record['id'] = seq_id
    record['external_id'] = external_id
    record['acao_noturna'] = record.get('acao_noturna', False)
    record['reincidencias'] = record.get('reincidencias', [])
    
    # Adicionar o novo registro ao DataFrame
    new_df = pd.concat([df, pd.Series(record).to_frame().T], ignore_index=True)
    
    # 2. Salvar no Sheets (Chamada corrigida)
    update_data_in_sheet(SHEET_NAME, new_df)
    
    return record 

def fetch_denuncia_by_id(id_):
    """Busca uma denúncia pelo ID sequencial (interno)."""
    df = fetch_all_denuncias_df()
    # Garante que o df['id'] é comparável ao id_ (int)
    record = df[pd.to_numeric(df['id'], errors='coerce') == id_]
    if not record.empty:
        return record.iloc[0].to_dict()
    return None

def update_denuncia_full(id_, new_data):
    """Atualiza um registro existente no Sheets."""
    df = fetch_all_denuncias_df()
    # Garante que o df['id'] é numérico para o índice
    df['id'] = pd.to_numeric(df['id'], errors='coerce')
    idx = df[df['id'] == id_].index
    
    if not idx.empty:
        # Merge os dados mantendo o ID e External ID (e colunas de controle)
        df.loc[idx, new_data.keys()] = new_data.values()
        
        # Salvar no Sheets (Chamada corrigida)
        update_data_in_sheet(SHEET_NAME, df)
        return True
    return False

def delete_denuncia(id_):
    """Deleta um registro do Sheets."""
    df = fetch_all_denuncias_df()
    df['id'] = pd.to_numeric(df['id'], errors='coerce')
    new_df = df[df['id'] != id_]
    
    if len(new_df) < len(df):
        # Salvar no Sheets (Chamada corrigida)
        update_data_in_sheet(SHEET_NAME, new_df)
        return True
    return False

# ---------------------- FPDF com Papel Timbrado e Reincidência ----------------------
# O código FPDF é mantido exatamente como você o forneceu (Linha 201 em diante)
# ...

class PDF(FPDF):
    """Classe PDF customizada com Papel Timbrado."""
    
    def __init__(self, orientation='P', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.letterhead_path = "Captura de tela 2025-12-11 155619.png"
        
        if 'uploaded_letterhead_path' not in st.session_state:
            try:
                if os.path.exists(self.letterhead_path):
                    st.session_state['uploaded_letterhead_path'] = self.letterhead_path
                else:
                    st.session_state['uploaded_letterhead_path'] = None
                    # Removido st.warning para evitar poluir a tela em cada execução
            except:
                st.session_state['uploaded_letterhead_path'] = None
        
        self.letterhead_path = st.session_state['uploaded_letterhead_path']

    def header(self):
        """Desenha o papel timbrado em cada página."""
        if self.letterhead_path:
            self.image(self.letterhead_path, 0, 0, self.w)
        self.set_y(40) 

    def footer(self):
        """Rodapé da página."""
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, 'Página %s' % self.page_no(), 0, 0, 'C')

def add_record_details_to_pdf(pdf, record, is_reincidencia=False, reincidencia_num=0):
    """Adiciona os detalhes de uma denúncia/reincidência à página do PDF."""
    
    if is_reincidencia:
        title = f"Reincidência #{reincidencia_num} - OS Nº {record['external_id']}"
        date_time = f"Data/Hora Reincidência: {record['data_reincidencia']}" 
        origem = f"Origem: {record['origem_reincidencia']}" 
    else:
        title = f"Ordem de Serviço Nº {record['external_id']}"
        date_time = f"Data/Hora: {record['created_at']}"
        origem = f"Origem: {record['origem']}"

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, title, ln=True, align='L')
    pdf.ln(2)

    pdf.set_font("Arial", "", 11)
    
    details = f"""
{date_time}
{origem}
Tipo: {record['tipo']}
Endereço: {record['rua']}, {record['numero']}
Bairro/Zona: {record['bairro']} / {record['zona']}
Quem recebeu: {record['quem_recebeu']}
Status: {record['status']}
"""
    pdf.multi_cell(0, 6, details)
    pdf.ln(4)
    
    # Descrição
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 6, "DESCRIÇÃO DA ORDEM DE SERVIÇO / REINCIDÊNCIA:", ln=True)
    
    pdf.set_font("Arial", "", 10)
    description = record.get('descricao_reincidencia') if is_reincidencia else record['descricao']
    
    pdf.set_fill_color(240, 240, 240)
    pdf.multi_cell(0, 5, description, 1, 'L', 1)
    
    pdf.ln(6)
    
    # Campo Observações 
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 6, "OBSERVAÇÕES DE CAMPO / AÇÕES REALIZADAS:", ln=True)
    
    pdf.multi_cell(0, 6, " " * 100, 1, 'L', 0)
    pdf.ln(1)


def create_pdf_from_record(record):
    """Gera o PDF com registro principal na 1ª página e reincidências nas páginas seguintes."""
    
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    
    # --- Página 1: Denúncia Principal ---
    pdf.add_page()
    add_record_details_to_pdf(pdf, record, is_reincidencia=False)
    
    # --- Páginas Subsequentes: Reincidências ---
    reincidencias = record.get('reincidencias', [])
    if reincidencias:
        for i, reinc in enumerate(reincidencias, 1):
            pdf.add_page()
            full_reinc_record = {**record, **reinc}
            add_record_details_to_pdf(pdf, full_reinc_record, is_reincidencia=True, reincidencia_num=i)

    # Retorna o PDF como bytes
    pdf_bytes = pdf.output(dest="S")
    return bytes(pdf_bytes) if isinstance(pdf_bytes, bytearray) else pdf_bytes

# ---------------------- Utilities ----------------------

def safe_index(lista, valor, padrao=0):
    """Retorna o índice do valor na lista de forma segura, evitando crash."""
    try:
        return lista.index(valor)
    except ValueError:
        return padrao

def load_users():
    if not os.path.exists(USERS_PATH):
        with open(USERS_PATH, 'w') as f:
            json.dump([], f)
    with open(USERS_PATH, 'r') as f:
        try:
            return json.load(f)
        except:
            return []

def save_users(users):
    with open(USERS_PATH, 'w') as f:
        json.dump(users, f, indent=2)

def hash_password(password: str):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def add_user(username, password, full_name=""):
    users = load_users()
    if any(u['username'] == username for u in users):
        return False
    users.append({'username': username, 'password': hash_password(password), 'full_name': full_name})
    save_users(users)
    return True

def verify_user(username, password):
    # Admin fixo
    if username == 'admin' and password == 'fisc2023':
        return {'username':'admin','full_name':'Administrador','is_admin':True}
    
    users = load_users()
    for u in users:
        if u['username'] == username and u['password'] == hash_password(password):
            return {'username':username,'full_name':u.get('full_name', username),'is_admin':False}
    return None

# ---------------------- CALLBACK DE FORMULÁRIO ----------------------

def handle_form_submit(origem, tipo, rua, numero, bairro, zona, lat, lon, descricao, fotos, quem_recebeu, acao_noturna):
    """Função que processa o formulário de registro após o clique em 'Salvar'."""
    
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 1. Salvar Arquivos de Fotos (localmente)
    saved_files = []
    if fotos:
        prev_external_id, _ = generate_external_id(fetch_all_denuncias_df()) 
        for f in fotos:
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            safe_name = f.name.replace(" ", "_")
            filename = f"{prev_external_id.replace('/','_')}_{timestamp}_{safe_name}"
            path = os.path.join(UPLOADS_DIR, filename)
            with open(path, 'wb') as out:
                out.write(f.read())
            saved_files.append(path)
    
    # 2. Montar o Registro
    record = {
        'created_at': created_at,
        'origem': origem,
        'tipo': tipo,
        'rua': rua,
        'numero': numero,
        'bairro': bairro,
        'zona': zona,
        'latitude': lat,
        'longitude': lon,
        'descricao': descricao,
        'fotos': saved_files,
        'quem_recebeu': quem_recebeu,
        'status': 'Pendente',
        'acao_noturna': acao_noturna,
        'reincidencias': []
    }
    
    # 3. Inserir no Google Sheets
    inserted_record = insert_denuncia(record)
    st.success(f"Denúncia {inserted_record['external_id']} salva com sucesso!")

    # 4. Tentar Gerar o PDF
    try:
        pdf_bytes = create_pdf_from_record(inserted_record)
        
        if pdf_bytes and isinstance(pdf_bytes, bytes):
            st.session_state['download_pdf_data'] = pdf_bytes
            st.session_state['download_pdf_id'] = inserted_record['external_id']
            
            if 'last_edited_pdf' in st.session_state:
                del st.session_state['last_edited_pdf']
        else:
            st.warning("⚠️ Falha na geração do PDF. O registro foi salvo, mas o documento não está disponível.")

    except Exception as e:
        st.error(f"⚠️ Erro grave na geração do PDF: {e}")
        
    st.rerun()

# ---------------------- Init (Funções de Autenticação/Inicialização) ----------------------

if 'user' not in st.session_state:
    st.session_state['user'] = None
    
# Tenta conectar ao Google Sheets (usa a nova classe SheetsClient)
if SheetsClient.get_client() is None:
    # Se get_client falhar, ele já exibe o erro e retorna None
    st.stop()
    
# ---------------------- Layout & CSS ----------------------
st.markdown("""
<style>
header {visibility: hidden}
footer {visibility: hidden}

/* Fundo da Sidebar */
.sidebar .sidebar-content {
    background: linear-gradient(#0b3b2e, #2f6f4f);
}

/* Estilo do Título Principal */
.h1-urb {font-weight:800; color: #003300;}

/* Estiliza o título do APP na BARRA LATERAL */
[data-testid="stSidebar"] .st-emotion-cache-p5m9y8 p {
    color: #DAA520; 
    font-weight: bold;
    font-size: 1.1em;
}

</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1,4])
with col2:
    st.markdown("<h1 class='h1-urb'>URB <span style='color:#DAA520'>Fiscalização - Denúncias</span></h1>", unsafe_allow_html=True)
    st.write("")

# ---------------------- Authentication ----------------------
if st.session_state['user'] is None:
    st.subheader("Login")
    login_col1, login_col2 = st.columns(2)
    with login_col1:
        username = st.text_input('Usuário')
    with login_col2:
        password = st.text_input('Senha', type='password')
    if st.button('Entrar'):
        user = verify_user(username.strip(), password)
        if user:
            st.session_state['user'] = user
            st.rerun()
        else:
            st.error('Usuário ou senha incorretos')
    st.info("Administrador: usuário 'admin' / senha 'fisc2023'")
    st.stop()

user = st.session_state['user']
st.sidebar.markdown("<h3 style='color:#DAA520; font-weight:bold;'>URB Fiscalização</h3>", unsafe_allow_html=True)
st.sidebar.markdown("---") 
st.sidebar.markdown(f"**Usuário:** {user['full_name']} ({user['username']})")
if user.get('is_admin'):
    st.sidebar.success('Administrador')

# ---------------------- Navigation ----------------------
pages = ["Registro da denuncia", "Historico"]
if user.get('is_admin'):
    pages.insert(0, 'Admin - Gestão de Usuários')
page = st.sidebar.selectbox('Navegação', pages)

# ---------------------- Page: Admin ----------------------
if page == 'Admin - Gestão de Usuários':
    st.header('Administração - Cadastrar novos usuários')
    with st.form('add_user'):
        new_username = st.text_input('Nome de usuário')
        new_fullname = st.text_input('Nome completo')
        new_password = st.text_input('Senha', type='password')
        submitted = st.form_submit_button('Adicionar usuário')
        if submitted:
            if new_username and new_password:
                ok = add_user(new_username.strip(), new_password.strip(), new_fullname.strip())
                if ok:
                    st.success('Usuário criado com sucesso')
                else:
                    st.error('Usuário já existe')
            else:
                st.error('Preencha usuário e senha')
    st.markdown('---')
    users = load_users()
    if users:
        dfu = pd.DataFrame(users)
        if 'password' in dfu.columns:
            dfu = dfu.drop(columns=['password'])
        st.dataframe(dfu)
    st.stop()

# ---------------------- Page: Registro ----------------------
if page == 'Registro da denuncia':
    st.header('Registro da Denúncia')
    
    # Carrega o DF apenas para gerar a prévia do ID
    df_preview = fetch_all_denuncias_df()
    external_id_preview, _ = generate_external_id(df_preview)
    created_at_preview = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with st.form('registro'):
        
        st.write(f"**Id da denúncia (Prévia):** {external_id_preview}")
        st.write(f"**Data e Hora:** {created_at_preview}")

        origem = st.selectbox('Origem da denúncia', OPCOES_ORIGEM, key='f_origem')
        tipo = st.selectbox('Tipo de denúncia', OPCOES_TIPO, key='f_tipo')
        
        c0, c_acao_noturna = st.columns([3, 1])
        with c_acao_noturna:
            acao_noturna = st.checkbox("Ação Noturna", key='f_acao_noturna')

        c1, c2 = st.columns(2)
        rua = c1.text_input('Nome da rua', key='f_rua')
        numero = c2.text_input('Número', key='f_numero')
        
        bairro = st.selectbox('Bairro', OPCOES_BAIRROS, key='f_bairro')
        zona = st.selectbox('Zona', OPCOES_ZONA, key='f_zona')
        
        c3, c4 = st.columns(2)
        lat = c3.text_input('Latitude', key='f_lat')
        lon = c4.text_input('Longitude', key='f_lon')
        
        if lat and lon:
            # Corrigido o link do Google Maps
            maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            st.markdown(f"[Abrir localização no Google Maps]({maps_link})")
            
        descricao = st.text_area('Descrição da Ordem de Serviço', height=150, key='f_descricao')
        fotos = st.file_uploader('Anexar fotos (várias)', type=['png','jpg','jpeg'], accept_multiple_files=True, key='f_fotos')
        quem_recebeu = st.selectbox('Quem recebeu a denúncia', OPCOES_FISCAIS, key='f_quem_recebeu')

        # Chamada ao callback
        st.form_submit_button(
            'Salvar denúncia',
            on_click=handle_form_submit,
            args=(origem, tipo, rua, numero, bairro, zona, lat, lon, descricao, fotos, quem_recebeu, acao_noturna)
        )

    # Botão de PDF persistente 
    if 'download_pdf_data' in st.session_state and 'download_pdf_id' in st.session_state:
        
        pdf_data = st.session_state['download_pdf_data']
        pdf_id = st.session_state['download_pdf_id']
        
        st.markdown("---")
        st.subheader("Documento Gerado")
        
        col_down, col_clear = st.columns([1,1])
        with col_down:
            st.download_button(
                label='📥 Baixar Ordem de Serviço (PDF)', 
                data=pdf_data, 
                file_name=f"OS_{pdf_id.replace('/', '_')}.pdf", 
                mime='application/pdf'
            )
        with col_clear:
            if st.button("Limpar / Novo Registro"):
                if 'download_pdf_data' in st.session_state:
                    del st.session_state['download_pdf_data']
                    del st.session_state['download_pdf_id']
                if 'last_edited_pdf' in st.session_state:
                    del st.session_state['last_edited_pdf']
                st.rerun()


# ---------------------- Page: Historico ----------------------
if page == 'Historico':
    st.header('Histórico de Denúncias')
    
    # Limpar estados de edição/reincidência/download ao mudar de página
    if 'edit_mode_id' in st.session_state: del st.session_state['edit_mode_id']
    if 'reinc_mode_id' in st.session_state: del st.session_state['reinc_mode_id']
    if 'download_pdf_data' in st.session_state: 
        del st.session_state['download_pdf_data']
        del st.session_state['download_pdf_id']


    df = fetch_all_denuncias_df()
    
    if df.empty:
        st.info('Nenhuma denúncia registrada ainda.')
        st.stop()

    # Garantir que 'id' é numérico
    df['id'] = pd.to_numeric(df['id'], errors='coerce')
    df = df.dropna(subset=['id']).astype({'id': int})
    
    display_df = df.copy()
    display_df['created_at'] = pd.to_datetime(display_df['created_at'], errors='coerce')
    # Ajuste de erro: 'dias_passados' só pode ser calculado se 'created_at' for válido
    valid_dates = display_df['created_at'].dropna()
    display_df['dias_passados'] = pd.Series(dtype='int') # Inicializa a coluna
    display_df.loc[valid_dates.index, 'dias_passados'] = (pd.Timestamp(datetime.now()) - valid_dates).dt.days
    display_df['dias_passados'] = display_df['dias_passados'].fillna(0).astype(int)

    # Campo para indicar se tem reincidências
    display_df['Tem Reincidência'] = display_df['reincidencias'].apply(lambda x: '✅ Sim' if x else '❌ Não')
    display_df['Ação Noturna'] = display_df['acao_noturna'].apply(lambda x: '🌙 Sim' if x else 'Não')

    # Filtros
    st.subheader('Pesquisar / Filtrar')
    cols = st.columns(4)
    q_ext = cols[0].text_input('Id (ex: 0001/2025)')
    q_status = cols[1].selectbox('Status', options=['Todos'] + OPCOES_STATUS)
    q_acao_noturna = cols[2].selectbox('Ação Noturna', options=['Todos', 'Sim', 'Não'])
    q_text = cols[3].text_input('Texto na descrição')

    mask = pd.Series([True]*len(display_df))
    if q_ext:
        mask = mask & display_df['external_id'].str.contains(q_ext, na=False)
    if q_status and q_status != 'Todos':
        mask = mask & (display_df['status'] == q_status)
    if q_acao_noturna == 'Sim':
        mask = mask & (display_df['acao_noturna'] == True)
    elif q_acao_noturna == 'Não':
        mask = mask & (display_df['acao_noturna'] == False)
    if q_text:
        main_desc_mask = display_df['descricao'].astype(str).str.contains(q_text, na=False, case=False)
        reinc_desc_mask = display_df['reincidencias'].astype(str).str.contains(q_text, na=False, case=False)
        mask = mask & (main_desc_mask | reinc_desc_mask)

    filtered = display_df[mask].sort_values(by='id', ascending=False)

    # Exibição
    st.subheader(f'Resultados ({len(filtered)})')
    
    styled_df = filtered[['id','external_id','created_at','origem','tipo','bairro','Ação Noturna','Tem Reincidência', 'quem_recebeu','status','dias_passados']].copy()
    styled_df['created_at'] = styled_df['created_at'].dt.strftime('%d/%m/%Y %H:%M')

    st.dataframe(styled_df, use_container_width=True)

    # Ações em Lote 
    st.markdown('---')
    sel_ids = st.multiselect('Selecione IDs para Ações em Massa', options=filtered['id'].tolist())
    
    if sel_ids:
        action_col1, action_col2, action_col3, action_col4 = st.columns(4)
        with action_col1:
            if st.button('✅ Marcar como Concluída'):
                for i in sel_ids:
                    update_denuncia_full(i, {'status': 'Concluída'})
                st.success('Atualizado!')
                st.rerun()
        with action_col2:
            if st.button('🔄 Marcar como Pendente'):
                for i in sel_ids:
                    update_denuncia_full(i, {'status': 'Pendente'})
                st.success('Atualizado!')
                st.rerun()
        with action_col3:
            if st.button('🗑️ Excluir Selecionados'):
                for i in sel_ids:
                    delete_denuncia(i)
                st.success('Excluído(s)!')
                st.rerun()
        with action_col4:
            if st.button('⬇️ Exportar CSV'):
                export_df = df[df['id'].isin(sel_ids)].copy()
                csv = export_df.to_csv(index=False).encode('utf-8')
                st.download_button('Baixar CSV', csv, file_name='denuncias_selecionadas.csv', mime='text/csv')

    st.markdown('---')
    
    # ---------------------- Editar Denúncia / Adicionar Reincidência ----------------------
    st.subheader('Opções por ID: Editar / Reincidência')
    edit_id = st.number_input('ID interno da denúncia', min_value=1, step=1, key='action_id_input')
    
    col_load_edit, col_load_reinc = st.columns(2)
    
    # Botão para carregar o formulário de edição
    with col_load_edit:
        if st.button('✍️ Carregar para Edição'):
            st.session_state['edit_mode_id'] = int(edit_id)
            if 'reinc_mode_id' in st.session_state: del st.session_state['reinc_mode_id']
            if 'download_pdf_data' in st.session_state: 
                del st.session_state['download_pdf_data']
                del st.session_state['download_pdf_id']
            if 'last_edited_pdf' in st.session_state: del st.session_state['last_edited_pdf']
            st.rerun()

    # Botão para carregar o formulário de reincidência
    with col_load_reinc:
        if st.button('➕ Adicionar Reincidência'):
            st.session_state['reinc_mode_id'] = int(edit_id)
            if 'edit_mode_id' in st.session_state: del st.session_state['edit_mode_id']
            if 'download_pdf_data' in st.session_state: 
                del st.session_state['download_pdf_data']
                del st.session_state['download_pdf_id']
            if 'last_edited_pdf' in st.session_state: del st.session_state['last_edited_pdf']
            st.rerun()
            
    # --- Formulário de Edição ---
    if 'edit_mode_id' in st.session_state:
        target_id = st.session_state['edit_mode_id']
        rec = fetch_denuncia_by_id(target_id)
        
        if not rec:
            st.error('ID não encontrado')
            if 'edit_mode_id' in st.session_state: del st.session_state['edit_mode_id']
            st.stop()
        else:
            st.info(f"✍️ Editando Denúncia Principal: {rec['external_id']}")
            
            with st.form('edit_form'):
                idx_origem = safe_index(OPCOES_ORIGEM, rec.get('origem'))
                idx_tipo = safe_index(OPCOES_TIPO, rec.get('tipo'))
                idx_bairro = safe_index(OPCOES_BAIRROS, rec.get('bairro'))
                idx_zona = safe_index(OPCOES_ZONA, rec.get('zona'))
                idx_fiscal = safe_index(OPCOES_FISCAIS, rec.get('quem_recebeu'))
                idx_status = safe_index(OPCOES_STATUS, rec.get('status'))
                
                c_e1, c_e2, c_e3 = st.columns(3)
                origem_e = c_e1.selectbox('Origem', OPCOES_ORIGEM, index=idx_origem)
                tipo_e = c_e2.selectbox('Tipo', OPCOES_TIPO, index=idx_tipo)
                status_e = c_e3.selectbox('Status', OPCOES_STATUS, index=idx_status)

                acao_noturna_e = st.checkbox("Ação Noturna", value=rec.get('acao_noturna', False), key='e_acao_noturna')

                rua_e = st.text_input('Rua', value=rec.get('rua'))
                numero_e = st.text_input('Número', value=rec.get('numero'))
                
                bairro_e = st.selectbox('Bairro', OPCOES_BAIRROS, index=idx_bairro)
                zona_e = st.selectbox('Zona', OPCOES_ZONA, index=idx_zona)
                
                lat_e = st.text_input('Latitude', value=rec.get('latitude'))
                lon_e = st.text_input('Longitude', value=rec.get('longitude'))
                desc_e = st.text_area('Descrição', value=rec.get('descricao'))
                
                quem_e = st.selectbox('Quem recebeu', OPCOES_FISCAIS, index=idx_fiscal)
                
                submitted_e = st.form_submit_button('Salvar alterações')
                
                if submitted_e:
                    newrow = {
                        'origem': origem_e,
                        'tipo': tipo_e,
                        'rua': rua_e,
                        'numero': numero_e,
                        'bairro': bairro_e,
                        'zona': zona_e,
                        'latitude': lat_e,
                        'longitude': lon_e,
                        'descricao': desc_e,
                        'quem_recebeu': quem_e,
                        'status': status_e,
                        'acao_noturna': acao_noturna_e,
                    }
                    if update_denuncia_full(target_id, newrow):
                        # Gera o PDF atualizado após a edição
                        rec_updated = fetch_denuncia_by_id(target_id)
                        pdf_bytes = create_pdf_from_record(rec_updated)
                        
                        st.session_state['download_pdf_data'] = pdf_bytes
                        st.session_state['download_pdf_id'] = rec_updated['external_id']
                        st.session_state['last_edited_pdf'] = True # Sinaliza que este PDF é de uma edição
                        
                        st.success(f"Denúncia {rec_updated['external_id']} atualizada com sucesso!")
                        st.rerun()

    # --- Formulário de Reincidência ---
    if 'reinc_mode_id' in st.session_state:
        target_id = st.session_state['reinc_mode_id']
        rec = fetch_denuncia_by_id(target_id)
        
        if not rec:
            st.error('ID não encontrado')
            if 'reinc_mode_id' in st.session_state: del st.session_state['reinc_mode_id']
            st.stop()
        else:
            st.info(f"➕ Adicionando Reincidência para: {rec['external_id']}")
            
            with st.form('reincidencia_form'):
                data_reinc = st.date_input('Data da Reincidência', value=datetime.now().date())
                hora_reinc = st.time_input('Hora da Reincidência', value=datetime.now().time())
                origem_reinc = st.selectbox('Origem da Reincidência', OPCOES_ORIGEM)
                desc_reinc = st.text_area('Descrição da Reincidência/Ação de Campo', height=150)
                
                submitted_r = st.form_submit_button('Registrar Reincidência')
                
                if submitted_r:
                    
                    data_hora_reinc = f"{data_reinc.strftime('%Y-%m-%d')} {hora_reinc.strftime('%H:%M:%S')}"
                    
                    new_reincidencia = {
                        'data_reincidencia': data_hora_reinc,
                        'origem_reincidencia': origem_reinc,
                        'descricao_reincidencia': desc_reinc
                    }
                    
                    # Carrega as reincidências existentes
                    reincidencias_atuais = rec.get('reincidencias', [])
                    # Adiciona a nova
                    reincidencias_atuais.append(new_reincidencia)
                    
                    # Prepara a atualização
                    update_payload = {
                        'reincidencias': reincidencias_atuais,
                        # Opcional: Mudar o status da OS principal após a reincidência
                        'status': 'Em Andamento' 
                    }
                    
                    if update_denuncia_full(target_id, update_payload):
                        # Gera o PDF atualizado após a reincidência
                        rec_updated = fetch_denuncia_by_id(target_id)
                        pdf_bytes = create_pdf_from_record(rec_updated)
                        
                        st.session_state['download_pdf_data'] = pdf_bytes
                        st.session_state['download_pdf_id'] = rec_updated['external_id']
                        st.session_state['last_edited_pdf'] = True # Sinaliza que este PDF é de uma edição
                        
                        st.success(f"Reincidência registrada para {rec_updated['external_id']}!")
                        st.rerun()

    # Botão de PDF persistente para Histórico (Edição/Reincidência)
    if 'last_edited_pdf' in st.session_state and 'download_pdf_data' in st.session_state:
        st.markdown("---")
        st.subheader("Documento Atualizado")
        
        pdf_data = st.session_state['download_pdf_data']
        pdf_id = st.session_state['download_pdf_id']
        
        col_down, col_clear = st.columns([1,1])
        with col_down:
            st.download_button(
                label=f'⬇️ Baixar OS Atualizada (PDF)', 
                data=pdf_data, 
                file_name=f"OS_{pdf_id.replace('/', '_')}_ATUALIZADA.pdf", 
                mime='application/pdf'
            )
        with col_clear:
            if st.button("Limpar Ação"):
                del st.session_state['last_edited_pdf']
                del st.session_state['edit_mode_id']
                if 'reinc_mode_id' in st.session_state: del st.session_state['reinc_mode_id']
                del st.session_state['download_pdf_data']
                del st.session_state['download_pdf_id']
                st.rerun()




















