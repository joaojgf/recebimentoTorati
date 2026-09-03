import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
import io
import re
import os
from datetime import datetime

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(page_title="Torati Gestão Logística - Recebimento", layout="wide")
st.title("🏷️ Torati Gestão Logística - Recebimento")

# Arquivo CSV para persistência dos dados de cobrança
HISTORICO_FILE = "historico_etiquetas.csv"

def carregar_historico():
    """Carrega o histórico de impressões ou cria uma estrutura vazia."""
    if os.path.exists(HISTORICO_FILE):
        df = pd.read_csv(HISTORICO_FILE)
        df['Data_Emissao'] = pd.to_datetime(df['Data_Emissao'], errors='coerce')
        return df
    else:
        return pd.DataFrame(columns=[
            "Data_Hora_Registro", "Numero_NF", "Destinatario", 
            "Emitente", "Qtd_Etiquetas", "Data_Emissao", "Mes_Ano"
        ])

def salvar_registro(numero_nf, destinatario, emitente, qtd_etiquetas, data_emissao_str):
    """Registra uma nova impressão no histórico."""
    df = carregar_historico()
    
    # Tratamento da data
    try:
        data_dt = datetime.strptime(data_emissao_str, '%d/%m/%Y')
        mes_ano = data_dt.strftime('%m/%Y')
    except Exception:
        data_dt = datetime.now()
        mes_ano = datetime.now().strftime('%m/%Y')

    novo_registro = {
        "Data_Hora_Registro": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "Numero_NF": str(numero_nf),
        "Destinatario": str(destinatario).upper().strip(),
        "Emitente": str(emitente).strip(),
        "Qtd_Etiquetas": int(qtd_etiquetas),
        "Data_Emissao": data_dt.strftime('%Y-%m-%d'),
        "Mes_Ano": mes_ano
    }

    df = pd.concat([df, pd.DataFrame([novo_registro])], ignore_index=True)
    df.to_csv(HISTORICO_FILE, index=False)

# --- BARRA LATERAL: Configuração da Impressora (Padrão 60x40mm) ---
st.sidebar.header("⚙️ Configuração da Etiqueta")
largura_mm = st.sidebar.number_input("Largura (mm)", value=60, min_value=20, max_value=200)
altura_mm = st.sidebar.number_input("Altura (mm)", value=40, min_value=15, max_value=200)

def limpar_sku(sku_raw):
    """Remove colchetes, espaços e caracteres especiais para gerar código de barras limpo"""
    if not sku_raw:
        return ""
    return re.sub(r'[^a-zA-Z0-9\-]', '', str(sku_raw)).strip()

def gerar_pdf_etiquetas(produtos_com_qtd, largura, altura):
    buffer = io.BytesIO()
    largura_pt = largura * mm
    altura_pt = altura * mm
    c = canvas.Canvas(buffer, pagesize=(largura_pt, altura_pt))

    styles = getSampleStyleSheet()
    
    estilo_sku = ParagraphStyle(
        'SKU_Style',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        spaceAfter=1
    )
    
    estilo_desc = ParagraphStyle(
        'Desc_Style',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9
    )

    for item in produtos_com_qtd:
        sku_original = str(item['SKU'])
        sku_limpo = limpar_sku(sku_original)
        descricao = str(item['Descrição do Produto'])
        qtd_imprimir = int(item['Quantidade de Etiquetas'])

        for _ in range(qtd_imprimir):
            margem_x = 3 * mm
            margem_topo = 3 * mm
            margem_fundo = 3 * mm
            largura_util = largura_pt - (2 * margem_x)

            # 1. Desenha o SKU Limpo no topo
            p_sku = Paragraph(f"<b>SKU: {sku_limpo}</b>", estilo_sku)
            w_sku, h_sku = p_sku.wrap(largura_util, altura_pt)
            y_atual = altura_pt - margem_topo - h_sku
            p_sku.drawOn(c, margem_x, y_atual)

            # 2. Desenha a Descrição
            p_desc = Paragraph(descricao, estilo_desc)
            w_desc, h_desc = p_desc.wrap(largura_util, y_atual)
            y_atual -= (h_desc + 1.5 * mm)
            p_desc.drawOn(c, margem_x, y_atual)

            # 3. Código de Barras
            espaco_disponivel = y_atual - margem_fundo - (4 * mm)
            altura_barras = min(14 * mm, max(8 * mm, espaco_disponivel))
            
            tam_sku = max(len(sku_limpo), 4)
            largura_unidade_barra = min(0.38 * mm, largura_util / (tam_sku * 11 + 35))
            
            bc = code128.Code128(
                sku_limpo, 
                barHeight=altura_barras, 
                barWidth=largura_unidade_barra,
                humanReadable=False
            )
            
            pos_y_barras = margem_fundo + (3.5 * mm)
            pos_x_barras = (largura_pt - bc.width) / 2
            pos_x_barras = max(margem_x, pos_x_barras)
            
            bc.drawOn(c, pos_x_barras, pos_y_barras)

            # 4. Texto legível do código
            c.setFont("Helvetica", 7.5)
            c.drawCentredString(largura_pt / 2, margem_fundo, sku_limpo)

            c.showPage()

    c.save()
    buffer.seek(0)
    return buffer

# --- CRIAÇÃO DAS ABAS ---
aba_recebimento, aba_relatorio = st.tabs(["📦 Recebimento & Etiquetas", "📊 Relatório de Cobrança"])

# ==========================================
# ABA 1: RECEBIMENTO & ETIQUETAS
# ==========================================
with aba_recebimento:
    xml_file = st.file_uploader("Anexe o arquivo XML da Nota Fiscal", type=["xml"])

    if xml_file is not None:
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

            # Extração dos Dados Principais
            n_nf = root.find('.//nfe:ide/nfe:nNF', ns)
            numero_nota = n_nf.text if n_nf is not None else "N/A"

            emit = root.find('.//nfe:emit/nfe:xNome', ns)
            emitente = emit.text if emit is not None else "N/A"

            dest = root.find('.//nfe:dest/nfe:xNome', ns)
            destinatario = dest.text if dest is not None else "N/A"

            dh_emi = root.find('.//nfe:ide/nfe:dhEmi', ns)
            if dh_emi is None:
                dh_emi = root.find('.//nfe:ide/nfe:dEmi', ns)
            
            data_emissao = "N/A"
            if dh_emi is not None and dh_emi.text:
                try:
                    data_raw = dh_emi.text.split('T')[0]
                    data_emissao = datetime.strptime(data_raw, '%Y-%m-%d').strftime('%d/%m/%Y')
                except Exception:
                    data_emissao = dh_emi.text

            q_vol = root.find('.//nfe:transp/nfe:vol/nfe:qVol', ns)
            volumes = q_vol.text if q_vol is not None else "1"

            st.success(f"Nota Fiscal **{numero_nota}** recebida com sucesso!")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.caption("Fornecedor (Emitente)")
                st.markdown(f"<p style='font-size: 14px; font-weight: bold; margin-top: -8px;'>{emitente}</p>", unsafe_allow_html=True)
            with col2:
                st.caption("Cliente (Destinatário)")
                st.markdown(f"<p style='font-size: 14px; font-weight: bold; margin-top: -8px;'>{destinatario}</p>", unsafe_allow_html=True)
            with col3:
                st.caption("Data de Emissão")
                st.markdown(f"<p style='font-size: 14px; font-weight: bold; margin-top: -8px;'>{data_emissao}</p>", unsafe_allow_html=True)

            st.divider()

            # Mensagem do WhatsApp
            st.subheader("💬 Mensagem para o WhatsApp")
            mensagem_whatsapp = (
                f"Acusamos o recebimento da(s) seguinte(s) NF(s): {numero_nota} de {data_emissao}\n\n"
                f"Destinatário: {destinatario}\n"
                f"Fornecedor: {emitente}\n"
                f"VOLUMES: {volumes}"
            )
            st.code(mensagem_whatsapp, language=None)

            st.divider()

            # Extração de Produtos
            produtos = []
            for det in root.findall('.//nfe:det', ns):
                sku = det.find('.//nfe:prod/nfe:cProd', ns)
                descricao = det.find('.//nfe:prod/nfe:xProd', ns)
                quantidade = det.find('.//nfe:prod/nfe:qCom', ns)

                qtd_float = float(quantidade.text) if quantidade is not None else 1.0

                produtos.append({
                    "SKU": sku.text if sku is not None else "N/A",
                    "Descrição do Produto": descricao.text if descricao is not None else "N/A",
                    "Qtd. Nota Fiscal": int(qtd_float)
                })

            st.subheader("📦 Seleção e Ajuste de Etiquetas para Impressão")
            st.info("Abaixo você pode alterar manualmente a quantidade de etiquetas que deseja imprimir para cada produto.")

            produtos_para_impressao = []
            
            for idx, item in enumerate(produtos):
                col_info, col_qtd = st.columns([3, 1])
                with col_info:
                    st.write(f"**SKU:** {limpar_sku(item['SKU'])} | **Item:** {item['Descrição do Produto']}")
                    st.caption(f"Quantidade constante na Nota Fiscal: {item['Qtd. Nota Fiscal']}")
                with col_qtd:
                    qtd_desejada = st.number_input(
                        label="Qtd. Etiquetas",
                        min_value=0,
                        value=item['Qtd. Nota Fiscal'],
                        step=1,
                        key=f"qtd_input_{idx}"
                    )
                
                if qtd_desejada > 0:
                    produtos_para_impressao.append({
                        "SKU": item["SKU"],
                        "Descrição do Produto": item["Descrição do Produto"],
                        "Quantidade de Etiquetas": qtd_desejada
                    })
                st.divider()

            # Botão de Download com registro no Histórico
            if produtos_para_impressao:
                total_etiquetas = sum(p["Quantidade de Etiquetas"] for p in produtos_para_impressao)
                pdf_data = gerar_pdf_etiquetas(produtos_para_impressao, largura_mm, altura_mm)

                def ao_clicar_download():
                    salvar_registro(numero_nota, destinatario, emitente, total_etiquetas, data_emissao)

                st.download_button(
                    label=f"🖨️ Baixar PDF com {total_etiquetas} Etiqueta(s) ({largura_mm}x{altura_mm}mm)",
                    data=pdf_data,
                    file_name=f"etiquetas_nfe_{numero_nota}.pdf",
                    mime="application/pdf",
                    on_click=ao_clicar_download
                )
            else:
                st.warning("Defina pelo menos 1 etiqueta para gerar o arquivo PDF.")

        except Exception as e:
            st.error(f"Erro ao processar o arquivo XML: {e}")

# ==========================================
# ABA 2: RELATÓRIO DE COBRANÇA
# ==========================================
with aba_relatorio:
    st.header("📊 Relatório Mensal de Cobrança de Etiquetas")
    df_historico = carregar_historico()

    if df_historico.empty:
        st.info("Nenhuma impressão registrada até o momento.")
    else:
        # Filtros no topo da aba
        col_filtro1, col_filtro2, col_filtro3 = st.columns(3)
        
        meses_disponiveis = sorted(df_historico['Mes_Ano'].unique().tolist(), reverse=True)
        with col_filtro1:
            mes_selecionado = st.selectbox("Selecione o Mês/Ano de Fechamento", meses_disponiveis)
        
        # Filtrar pelo Mês Selecionado
        df_mes = df_historico[df_historico['Mes_Ano'] == mes_selecionado]

        clientes_disponiveis = ["Todos os Clientes"] + sorted(df_mes['Destinatario'].unique().tolist())
        with col_filtro2:
            cliente_selecionado = st.selectbox("Filtrar por Cliente (Destinatário)", clientes_disponiveis)
        
        with col_filtro3:
            valor_por_etiqueta = st.number_input("Valor por Etiqueta (R$)", value=0.50, min_value=0.0, step=0.05, format="%.2f")

        if cliente_selecionado != "Todos os Clientes":
            df_mes = df_mes[df_mes['Destinatario'] == cliente_selecionado]

        st.divider()

        # Resumo de Totais
        total_etiquetas_mes = df_mes['Qtd_Etiquetas'].sum()
        total_faturado = total_etiquetas_mes * valor_por_etiqueta

        m1, m2, m3 = st.columns(3)
        m1.metric("Total de Etiquetas Impressas", f"{total_etiquetas_mes:,}".replace(",", "."))
        m2.metric("Valor Unitário", f"R$ {valor_por_etiqueta:.2f}")
        m3.metric("Total a Cobrar no Mês", f"R$ {total_faturado:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

        st.divider()

        # Tabela Consolidada por Cliente
        st.subheader("👥 Consolidado por Cliente (Para Faturamento)")
        df_consolidado = df_mes.groupby('Destinatario').agg(
            Notas_Processadas=('Numero_NF', 'nunique'),
            Total_Etiquetas=('Qtd_Etiquetas', 'sum')
        ).reset_index()

        df_consolidado['Valor_Total_R$'] = df_consolidado['Total_Etiquetas'] * valor_por_etiqueta
        df_consolidado.columns = ["Cliente (Destinatário)", "Qtd. Notas Fiscais", "Total Etiquetas", "Valor Total (R$)"]
        
        st.dataframe(df_consolidado, use_container_width=True)

        # Detalhamento por Nota Fiscal
        st.subheader("📜 Detalhamento por Nota Fiscal")
        st.dataframe(
            df_mes[['Data_Hora_Registro', 'Numero_NF', 'Destinatario', 'Emitente', 'Qtd_Etiquetas']],
            use_container_width=True
        )

        # Exportação do relatório para Excel/CSV
        csv_buffer = df_mes.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Exportar Relatório do Mês (CSV)",
            data=csv_buffer,
            file_name=f"cobranca_etiquetas_{mes_selecionado.replace('/', '_')}.csv",
            mime="text/csv"
        )
