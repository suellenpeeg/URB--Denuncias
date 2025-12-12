import streamlit as st
import pandas as pd
import gspread
import json
import time

# --- Constantes do Aplicativo (Ajuste se necessário) ---
SHEET_NAME = "Denuncias" 
SPREADSHEET_URL = st.secrets["general"]["spreadsheet_url"]

# --- 1. CONFIGURAÇÃO DA CONEXÃO GSPREAD (USANDO @st.cache_resource) ---

@st.cache_resource
def get_gspread_client():
    """
    Inicializa e armazena o cliente gspread.
    
    Usa @st.cache_resource para garantir que a conexão seja
    criada APENAS uma vez, evitando o erro UnhashableParamError
    ao tentar hashear o objeto 'gc' na leitura de dados.
    """
    try:
        # Carrega as credenciais do Streamlit Secrets
        secrets = st.secrets["gcp_service_account"]
        
        # O gspread service_account_from_dict espera um dict, não um objeto Secrets
        info = {
            "type": secrets.type,
            "project_id": secrets.project_id,
            "private_key_id": secrets.private_key_id,
            # Importante: A private_key PRECISA ser carregada com o json.loads
            # para que as quebras de linha '\n' sejam interpretadas corretamente.
            "private_key": secrets.private_key, 
            "client_email": secrets.client_email,
            "client_id": secrets.client_id,
            "auth_uri": secrets.auth_uri,
            "token_uri": secrets.token_uri,
            "auth_provider_x509_cert_url": secrets.auth_provider_x509_cert_url,
            "client_x509_cert_url": secrets.client_x509_cert_url,
            "universe_domain": secrets.universe_domain,
        }
        
        # Cria o cliente gspread a partir do dicionário de credenciais
        gc = gspread.service_account_from_dict(info)
        
        return gc
        
    except Exception as e:
        st.error(f"Erro ao autenticar no Google Sheets. Verifique o secrets.toml/painel de segredos.")
        st.exception(e)
        return None

# --- 2. FUNÇÃO DE LEITURA (USANDO @st.cache_data) ---

@st.cache_data(ttl=600) # O cache expira a cada 10 minutos para garantir atualização
def fetch_all_denuncias_df():
    """
    Busca todos os dados da planilha e retorna como DataFrame.
    
    Não recebe o cliente 'gc' diretamente para evitar UnhashableParamError.
    """
    gc = get_gspread_client()
    if not gc:
        return pd.DataFrame() # Retorna DataFrame vazio em caso de falha de conexão

    try:
        sh = gc.open_by_url(SPREADSHEET_URL)
        worksheet = sh.worksheet(SHEET_NAME)
        
        # Puxa todos os registros e converte para DataFrame
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Adiciona coluna de carimbo de data/hora se não existir
        if 'Timestamp' not in df.columns:
             df.insert(0, 'Timestamp', pd.to_datetime('now'))
             
        return df
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Erro: Planilha não encontrada no URL fornecido. URL: {SPREADSHEET_URL}")
        return pd.DataFrame()
    except gspread.exceptions.APIError as e:
        st.error(f"Erro de permissão ou API. Verifique se o e-mail da conta de serviço ({st.secrets['gcp_service_account'].client_email}) é Editor da planilha.")
        st.exception(e)
        return pd.DataFrame()
    except Exception as e:
        st.error("Ocorreu um erro desconhecido ao carregar os dados.")
        st.exception(e)
        return pd.DataFrame()

# --- 3. FUNÇÃO DE ESCRITA ---

def add_new_denuncia(new_data):
    """Adiciona uma nova linha de dados à planilha."""
    gc = get_gspread_client()
    if not gc:
        return False
        
    try:
        sh = gc.open_by_url(SPREADSHEET_URL)
        worksheet = sh.worksheet(SHEET_NAME)
        
        # Adiciona a nova linha de dados
        worksheet.append_row(new_data)
        
        # Invalida o cache para que o DataFrame seja atualizado na próxima chamada
        st.cache_data.clear() 
        return True
    
    except Exception as e:
        st.error("Erro ao salvar os dados na planilha.")
        st.exception(e)
        return False

# --- 4. INTERFACE STREAMLIT ---

def main():
    st.title("🚧 URB - Denúncias de Fiscalização")
    st.markdown("---")

    # --- Seção de Cadastro de Denúncia ---
    st.header("📝 Nova Denúncia")
    
    with st.form(key='denuncia_form'):
        
        # Campos do Formulário (Ajuste para corresponder às colunas da sua planilha)
        tipo = st.selectbox("Tipo de Denúncia", 
                            ['Construção Ilegal', 'Invasão de Terreno', 'Descarte Irregular', 'Outro'])
        local = st.text_input("Endereço/Local da Ocorrência", placeholder="Rua, Número, Bairro")
        descricao = st.text_area("Descrição Detalhada", height=150)
        nome_contato = st.text_input("Nome do Denunciante (Opcional)")
        telefone = st.text_input("Telefone de Contato (Opcional)")
        
        submit_button = st.form_submit_button(label='Registrar Denúncia')

        if submit_button:
            if not local or not descricao:
                st.warning("Por favor, preencha o Local e a Descrição.")
            else:
                # 1. Prepara os dados
                new_row = [
                    time.strftime("%Y-%m-%d %H:%M:%S"), # Timestamp
                    tipo,
                    local,
                    descricao,
                    nome_contato,
                    telefone,
                    "Pendente" # Status inicial
                ]
                
                # 2. Envia para a planilha
                if add_new_denuncia(new_row):
                    st.success("✅ Denúncia registrada com sucesso!")
                    time.sleep(1)
                    st.experimental_rerun() # Reinicia para exibir dados atualizados

    st.markdown("---")
    
    # --- Seção de Visualização dos Dados ---
    st.header("📋 Dados de Denúncias Registradas")
    
    # Chama a função cacheada para obter os dados
    df_denuncias = fetch_all_denuncias_df()

    if not df_denuncias.empty:
        st.metric(label="Total de Denúncias", value=len(df_denuncias))
        
        # Exibe a tabela (opcionalmente oculta colunas confidenciais)
        st.dataframe(df_denuncias, use_container_width=True)
    elif df_denuncias.empty and get_gspread_client():
        st.info("Nenhuma denúncia encontrada na planilha. Cadastre a primeira!")

# Executa o aplicativo
if __name__ == "__main__":
    main()


