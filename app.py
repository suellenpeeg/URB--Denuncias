
import streamlit as st
import pandas as pd
import json
import os
import sqlite3
from datetime import datetime
import hashlib
from io import BytesIO

# Configuração da Página
st.set_page_config(page_title="URB Fiscalização - Denúncias", layout="wide")

# PDF generation
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Constantes e Caminhos
DB_PATH = "denuncias.db"
USERS_PATH = "users.json"
UPLOADS_DIR = "uploads"

# Listas de Opções Globais (Para evitar inconsistências)
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

if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR, exist_ok=True)

# ---------------------- Utilities ----------------------

def safe_index(lista, valor, padrao=0):
    """Retorna o índice do valor na lista de forma segura, evitando crash."""
    try:
        return lista.index(valor)
    except ValueError:
        return padrao

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS denuncias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        external_id TEXT,
        created_at TEXT,
        origem TEXT,
        tipo TEXT,
        rua TEXT,
        numero TEXT,
        bairro TEXT,
        zona TEXT,
        latitude TEXT,
        longitude TEXT,
        descricao TEXT,
        fotos TEXT,
        quem_recebeu TEXT,
        status TEXT
    )''')
    conn.commit()
    conn.close()

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
    # Admin fixo (Recomendado usar st.secrets em produção)
    if username == 'admin' and password == 'fisc2023':
        return {'username':'admin','full_name':'Administrador','is_admin':True}
    
    users = load_users()
    for u in users:
        if u['username'] == username and u['password'] == hash_password(password):
            return {'username':username,'full_name':u.get('full_name', username),'is_admin':False}
    return None

def generate_external_id():
    """Gera ID baseado no último ID sequencial (MAX ID) para evitar duplicidade ao deletar."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT MAX(id) FROM denuncias')
    max_id = c.fetchone()[0]
    conn.close()
    
    next_id = (max_id + 1) if max_id is not None else 1
    year = datetime.now().year
    return f"{next_id:04d}/{year}"

def insert_denuncia(record):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO denuncias (external_id, created_at, origem, tipo, rua, numero, bairro, zona, latitude, longitude, descricao, fotos, quem_recebeu, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
        record['external_id'], record['created_at'], record['origem'], record['tipo'], record['rua'], record['numero'], record['bairro'], record['zona'], record['latitude'], record['longitude'], record['descricao'], json.dumps(record['fotos']), record['quem_recebeu'], record.get('status','Pendente')
    ))
    conn.commit()
    conn.close()

def fetch_all_denuncias():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query('SELECT * FROM denuncias ORDER BY id DESC', conn)
    conn.close()
    if not df.empty:
        # Tratamento seguro de JSON
        def safe_json_load(x):
            try:
                return json.loads(x) if x else []
            except:
                return []
        df['fotos'] = df['fotos'].apply(safe_json_load)
    return df

def update_denuncia_status(id_, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE denuncias SET status = ? WHERE id = ?', (status, id_))
    conn.commit()
    conn.close()

def delete_denuncia(id_):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM denuncias WHERE id = ?', (id_,))
    conn.commit()
    conn.close()

def update_denuncia_full(id_, row):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''UPDATE denuncias SET origem=?, tipo=?, rua=?, numero=?, bairro=?, zona=?, latitude=?, longitude=?, descricao=?, fotos=?, quem_recebeu=?, status=? WHERE id=?''', (
        row['origem'], row['tipo'], row['rua'], row['numero'], row['bairro'], row['zona'], row['latitude'], row['longitude'], row['descricao'], json.dumps(row['fotos']), row['quem_recebeu'], row['status'], id_
    ))
    conn.commit()
    conn.close()

def create_pdf_from_record(record):
    """Gera o PDF (ReportLab)"""
    buffer = BytesIO()

    fotos = []
    if record.get("fotos"):
        try:
            if isinstance(record["fotos"], list):
                fotos = record["fotos"]
            elif isinstance(record["fotos"], str):
                if record["fotos"].startswith("["):
                    fotos = json.loads(record["fotos"])
                else:
                    fotos = [f.strip() for f in record["fotos"].split(";") if f.strip()]
        except:
            fotos = []

    if REPORTLAB_AVAILABLE:
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 60

        # Cabeçalho
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, y, f"Ordem de Serviço Nº {record['external_id']}")
        y -= 40

        c.setFont("Helvetica", 11)
        info_lines = [
            f"Data/Hora: {record['created_at']}",
            f"Origem: {record['origem']}",
            f"Tipo: {record['tipo']}",
            f"Endereço: {record['rua']}, {record['numero']}",
            f"Bairro: {record['bairro']}",
            f"Zona: {record['zona']}",
            f"Latitude/Longitude: {record['latitude']} / {record['longitude']}",
            f"Quem recebeu: {record['quem_recebeu']}",
            "",
            "DESCRIÇÃO DA ORDEM DE SERVIÇO:",
        ]

        for ln in info_lines:
            c.drawString(50, y, ln)
            y -= 16

        # Descrição
        text_width = width - 100
        desc_lines = simpleSplit(record["descricao"], "Helvetica", 10, text_width)
        
        # Calcula altura necessária para descrição
        desc_box_height = max(len(desc_lines) * 14 + 20, 50)
        
        # Se descrição muito grande, quebra página? (Simplificado aqui: desenha até onde der)
        if y - desc_box_height < 100:
             c.showPage()
             y = height - 50

        c.rect(45, y - desc_box_height + 10, width - 90, desc_box_height, stroke=1, fill=0)

        text_y = y - 20
        c.setFont("Helvetica", 10)
        for line in desc_lines:
            c.drawString(55, text_y, line)
            text_y -= 14

        y -= desc_box_height + 40

        # Campo Observações
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "OBSERVAÇÕES DE CAMPO:")
        y -= 20

        obs_height = 12 * 14
        if y - obs_height < 50:
             c.showPage()
             y = height - 50
        
        c.rect(45, y - obs_height + 10, width - 90, obs_height, stroke=1, fill=0)
        c.showPage()

        # Página de Fotos
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, "FOTOS DA DENÚNCIA")

        if fotos:
            x = 50
            y = height - 150
            max_w = 200
            max_h = 200

            for foto_path in fotos:
                try:
                    abs_path = os.path.abspath(foto_path)
                    if os.path.exists(abs_path):
                        c.drawImage(abs_path, x, y, width=max_w, height=max_h, preserveAspectRatio=True, anchor='c')
                except Exception as e:
                    # print(f"Erro imagem: {e}") 
                    pass

                x += max_w + 20
                if x + max_w > width - 40:
                    x = 50
                    y -= max_h + 40
                    if y < 100:
                        c.showPage()
                        y = height - 150

        c.showPage()
        c.save()

        pdf = buffer.getvalue()
        buffer.close()
        return pdf

    # Fallback simples (FPDF) removido para simplificar, mas poderia manter
    return b""

# ---------------------- Init ----------------------
init_db()
if 'user' not in st.session_state:
    st.session_state['user'] = None

# ---------------------- Layout & CSS ----------------------
st.markdown("""
<style>
header {visibility: hidden}
footer {visibility: hidden}
.sidebar .sidebar-content {
    background: linear-gradient(#0b3b2e, #2f6f4f);
}
.h1-urb {font-weight:800; color: #003300;}
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
    st.info("Administrador: 'SUELLEN NASCIMENTO' ")
    st.stop()

user = st.session_state['user']
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
        # Esconde a senha no display
        if 'password' in dfu.columns:
            dfu = dfu.drop(columns=['password'])
        st.dataframe(dfu)
    st.stop()

# ---------------------- Page: Registro ----------------------
if page == 'Registro da denuncia':
    st.header('Registro da Denúncia')
    
    with st.form('registro'):
        # CORREÇÃO: Geração de ID baseada no MAX ID para evitar duplicidade
        external_id = generate_external_id()
        
        st.write(f"**Id da denúncia (Prévia):** {external_id}")
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        st.write(f"**Data e Hora:** {created_at}")

        origem = st.selectbox('Origem da denúncia', OPCOES_ORIGEM)
        tipo = st.selectbox('Tipo de denúncia', OPCOES_TIPO)
        
        c1, c2 = st.columns(2)
        rua = c1.text_input('Nome da rua')
        numero = c2.text_input('Número')
        
        bairro = st.selectbox('Bairro', OPCOES_BAIRROS)
        zona = st.selectbox('Zona', OPCOES_ZONA)
        
        c3, c4 = st.columns(2)
        lat = c3.text_input('Latitude')
        lon = c4.text_input('Longitude')
        
        if lat and lon:
            maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            st.markdown(f"[Abrir localização no Google Maps]({maps_link})")
            
        descricao = st.text_area('Descrição da Ordem de Serviço', height=150)
        fotos = st.file_uploader('Anexar fotos (várias)', type=['png','jpg','jpeg'], accept_multiple_files=True)
        quem_recebeu = st.selectbox('Quem recebeu a denúncia', OPCOES_FISCAIS)

        submitted = st.form_submit_button('Salvar denúncia')
        
        if submitted:
            saved_files = []
            if fotos:
                for f in fotos:
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    # Sanitiza nome do arquivo
                    safe_name = f.name.replace(" ", "_")
                    filename = f"{external_id.replace('/','_')}_{timestamp}_{safe_name}"
                    path = os.path.join(UPLOADS_DIR, filename)
                    with open(path, 'wb') as out:
                        out.write(f.read())
                    saved_files.append(path)
            
            record = {
                'external_id': external_id,
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
                'status': 'Pendente'
            }
            insert_denuncia(record)
            st.session_state['last_pdf_record'] = record
            st.success('Denúncia salva com sucesso!')

    # CORREÇÃO: Botão de PDF persistente até ser limpo ou novo registro
    if 'last_pdf_record' in st.session_state:
        st.markdown("---")
        st.subheader("Documento Gerado")
        
        rec = st.session_state['last_pdf_record']
        pdf_bytes = create_pdf_from_record(rec)
        
        col_down, col_clear = st.columns([1,1])
        with col_down:
            st.download_button(
                label='📥 Baixar Ordem de Serviço (PDF)', 
                data=pdf_bytes, 
                file_name=f"OS_{rec['external_id'].replace('/', '_')}.pdf", 
                mime='application/pdf'
            )
        with col_clear:
            if st.button("Limpar / Novo Registro"):
                del st.session_state['last_pdf_record']
                st.rerun()

# ---------------------- Page: Historico ----------------------
if page == 'Historico':
    st.header('Histórico de Denúncias')
    df = fetch_all_denuncias()
    
    if df.empty:
        st.info('Nenhuma denúncia registrada ainda.')
        st.stop()

    # Preparação para exibição
    display_df = df.copy()
    display_df['created_at'] = pd.to_datetime(display_df['created_at'])
    display_df['dias_passados'] = (pd.Timestamp(datetime.now()) - display_df['created_at']).dt.days

    # Filtros
    st.subheader('Pesquisar / Filtrar')
    cols = st.columns(4)
    q_ext = cols[0].text_input('Id (ex: 0001/2025)')
    q_status = cols[2].selectbox('Status', options=['Todos','Pendente','Concluída'])
    q_text = cols[3].text_input('Texto na descrição')

    mask = pd.Series([True]*len(display_df))
    if q_ext:
        mask = mask & display_df['external_id'].str.contains(q_ext, na=False)
    if q_status and q_status != 'Todos':
        mask = mask & (display_df['status'] == q_status)
    if q_text:
        mask = mask & display_df['descricao'].str.contains(q_text, na=False)

    filtered = display_df[mask]

    # Estilização
    st.subheader(f'Resultados ({len(filtered)})')
    
    styled_df = filtered[['id','external_id','created_at','origem','tipo','bairro','quem_recebeu','status','dias_passados']].copy()
    # Formata data para string limpa
    styled_df['created_at'] = styled_df['created_at'].dt.strftime('%d/%m/%Y %H:%M')

    def color_status(val):
        color = 'white'
        if val == 'Concluída':
            color = '#90EE90' # verde claro
        elif val == 'Pendente':
            color = '#FFB6C1' # vermelho claro
        return f'background-color: {color}; color: black'

    # Exibe tabela (sem estilização complexa para evitar bugs visuais, usando st.dataframe simples)
    st.dataframe(styled_df, use_container_width=True)

    # Ações em Lote
    sel_ids = st.multiselect('Selecione IDs para Ações em Massa', options=filtered['id'].tolist())
    
    if sel_ids:
        action_col1, action_col2, action_col3 = st.columns(3)
        with action_col1:
            if st.button('✅ Marcar como Concluída'):
                for i in sel_ids:
                    update_denuncia_status(i, 'Concluída')
                st.success('Atualizado!')
                st.rerun()
        with action_col2:
            if st.button('🗑️ Excluir Selecionados'):
                for i in sel_ids:
                    delete_denuncia(i)
                st.success('Excluído(s)!')
                st.rerun()
        with action_col3:
            if st.button('⬇️ Exportar CSV'):
                export_df = df[df['id'].isin(sel_ids)].copy()
                csv = export_df.to_csv(index=False)
                st.download_button('Baixar CSV', csv, file_name='denuncias_selecionadas.csv', mime='text/csv')

    st.markdown('---')
    
    # ---------------------- Editar Denúncia (Corrigido) ----------------------
    st.subheader('Editar Detalhes')
    edit_id = st.number_input('ID interno da denúncia a editar', min_value=1, step=1)
    
    if st.button('Carregar para edição'):
        st.session_state['edit_mode_id'] = int(edit_id)

    if 'edit_mode_id' in st.session_state:
        target_id = st.session_state['edit_mode_id']
        rec_matches = df[df['id']==target_id]
        
        if rec_matches.empty:
            st.error('ID não encontrado')
        else:
            rec = rec_matches.iloc[0]
            st.info(f"Editando ID: {rec['external_id']}")
            
            with st.form('edit_form'):
                # CORREÇÃO: Uso de safe_index para evitar travamento se o valor no banco for antigo/diferente
                idx_origem = safe_index(OPCOES_ORIGEM, rec['origem'])
                idx_tipo = safe_index(OPCOES_TIPO, rec['tipo'])
                idx_bairro = safe_index(OPCOES_BAIRROS, rec['bairro'])
                idx_zona = safe_index(OPCOES_ZONA, rec['zona'])
                idx_fiscal = safe_index(OPCOES_FISCAIS, rec['quem_recebeu'])
                
                c_e1, c_e2 = st.columns(2)
                origem_e = c_e1.selectbox('Origem', OPCOES_ORIGEM, index=idx_origem)
                tipo_e = c_e2.selectbox('Tipo', OPCOES_TIPO, index=idx_tipo)
                
                rua_e = st.text_input('Rua', value=rec['rua'])
                numero_e = st.text_input('Número', value=rec['numero'])
                
                bairro_e = st.selectbox('Bairro', OPCOES_BAIRROS, index=idx_bairro)
                zona_e = st.selectbox('Zona', OPCOES_ZONA, index=idx_zona)
                
                lat_e = st.text_input('Latitude', value=rec['latitude'])
                lon_e = st.text_input('Longitude', value=rec['longitude'])
                desc_e = st.text_area('Descrição', value=rec['descricao'])
                
                quem_e = st.selectbox('Quem recebeu', OPCOES_FISCAIS, index=idx_fiscal)
                
                # Status manual
                status_atual = rec['status']
                idx_status = 0 if status_atual == 'Pendente' else 1
                status_e = st.selectbox('Status', ['Pendente','Concluída'], index=idx_status)
                
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
                        'fotos': rec['fotos'], # Mantém fotos originais (upload na edição requer lógica extra)
                        'quem_recebeu': quem_e,
                        'status': status_e
                    }
                    update_denuncia_full(target_id, newrow)
                    st.success('Registro atualizado com sucesso!')
                    # Limpa modo de edição para refresh
                    del st.session_state['edit_mode_id']
                    st.rerun()

# ---------------------- Footer ----------------------
st.markdown('---')
st.caption('Aplicação URB Fiscalização - Versão Corrigida')