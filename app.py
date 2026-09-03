import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
import io
from datetime import datetime

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(page_title="Torati Gestão Logística - Recebimento", layout="wide")
st.title("🏷️ Torati Gestão Logística - Recebimento")

# --- BARRA LATERAL: Configuração da Impressora ---
st.sidebar.header("⚙️ Configuração da Etiqueta")
largura_mm = st.sidebar.number_input("Largura (mm)", value=100, min_value=20, max_value=200)
altura_mm = st.sidebar.number_input("Altura (mm)", value=50, min_value=15, max_value=200)

def gerar_pdf_etiquetas(produtos_com_qtd, largura, altura):
    """
    Gera o PDF das etiquetas utilizando a quantidade personalizada definida pelo usuário.
    """
    buffer = io.BytesIO()
    largura_pt = largura * mm
    altura_pt = altura * mm
    c = canvas.Canvas(buffer, pagesize=(largura_pt, altura_pt))

    styles = getSampleStyleSheet()
    
    estilo_sku = ParagraphStyle(
        'SKU_Style',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=13,
        spaceAfter=2
    )
    
    estilo_desc = ParagraphStyle(
        'Desc_Style',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11
    )

    for item in produtos_com_qtd:
        sku = str(item['SKU'])
        descricao = str(item['Descrição do Produto'])
        qtd_imprimir = int(item['Quantidade de Etiquetas'])

        for _ in range(qtd_imprimir):
            margem_x = 4 * mm
            margem_y = 3 * mm
            largura_util = largura_pt - (2 * margem_x)

            # 1. Desenha o SKU
            p_sku = Paragraph(f"<b>SKU: {sku}</b>", estilo_sku)
            w_sku, h_sku = p_sku.wrap(largura_util, altura_pt)
            y_atual = altura_pt - margem_y - h_sku
            p_sku.drawOn(c, margem_x, y_atual)

            # 2. Desenha a Descrição
            p_desc = Paragraph(descricao, estilo_desc)
            w_desc, h_desc = p_desc.wrap(largura_util, y_atual)
            y_atual -= (h_desc + 3 * mm)
            p_desc.drawOn(c, margem_x, y_atual)

            # 3. Código de Barras Expandido
            altura_barras = max(18 * mm, y_atual - margem_y - (5 * mm))
            largura_unidade_barra = (largura_util / (len(sku) * 11 + 35))
            
            bc = code128.Code128(
                sku, 
                barHeight=altura_barras, 
                barWidth=largura_unidade_barra,
                humanReadable=True
            )
            
            pos_x_barras = (largura_pt - bc.width) / 2
            pos_x_barras = max(margem_x, pos_x_barras)
            
            bc.drawOn(c, pos_x_barras, margem_y)
            c.showPage()

    c.save()
    buffer.seek(0)
    return buffer

# --- CORPO PRINCIPAL ---
xml_file = st.file_uploader("Anexe o arquivo XML da Nota Fiscal", type=["xml"])

if xml_file is not None:
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

        # 1. Extração dos Dados Principais (Número, Emitente, Destinatário)
        n_nf = root.find('.//nfe:ide/nfe:nNF', ns)
        numero_nota = n_nf.text if n_nf is not None else "N/A"

        emit = root.find('.//nfe:emit/nfe:xNome', ns)
        emitente = emit.text if emit is not None else "N/A"

        dest = root.find('.//nfe:dest/nfe:xNome', ns)
        destinatario = dest.text if dest is not None else "N/A"

        # Data de Emissão (Formatando de AAAA-MM-DD para DD/MM/AAAA)
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

        # Quantidade de Volumes da Carga
        q_vol = root.find('.//nfe:transp/nfe:vol/nfe:qVol', ns)
        volumes = q_vol.text if q_vol is not None else "1"

        # Exibição dos dados principais em colunas no painel superior
        st.success(f"Nota Fiscal **{numero_nota}** recebida com sucesso!")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Fornecedor (Emitente)", emitente)
        col2.metric("Cliente (Destinatário)", destinatario)
        col3.metric("Data de Emissão", data_emissao)

        # 2. Mensagem para o WhatsApp com Emitente e Destinatário
        st.subheader("💬 Mensagem para o WhatsApp")
        mensagem_whatsapp = (
            f"Acusamos o recebimento da(s) seguinte(s) NF(s): {numero_nota} de {data_emissao}\n\n"
            f"Destinatário: {destinatario}\n"
            f"Fornecedor: {emitente}\n"
            f"VOLUMES: {volumes}"
        )
        st.code(mensagem_whatsapp, language=None)

        st.divider()

        # 3. Extração dos Produtos
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

        # 4. Ajuste Manual da Quantidade de Etiquetas a Imprimir
        st.subheader("📦 Seleção e Ajuste de Etiquetas para Impressão")
        st.info("Abaixo você pode alterar manualmente a quantidade de etiquetas que deseja imprimir para cada produto.")

        produtos_para_impressao = []
        
        for idx, item in enumerate(produtos):
            col_info, col_qtd = st.columns([3, 1])
            with col_info:
                st.write(f"**SKU:** {item['SKU']} | **Item:** {item['Descrição do Produto']}")
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

        # 5. Botão de Download do PDF
        if produtos_para_impressao:
            total_etiquetas = sum(p["Quantidade de Etiquetas"] for p in produtos_para_impressao)
            pdf_data = gerar_pdf_etiquetas(produtos_para_impressao, largura_mm, altura_mm)

            st.download_button(
                label=f"🖨️ Baixar PDF com {total_etiquetas} Etiqueta(s) ({largura_mm}x{altura_mm}mm)",
                data=pdf_data,
                file_name=f"etiquetas_nfe_{numero_nota}.pdf",
                mime="application/pdf"
            )
        else:
            st.warning("Defina pelo menos 1 etiqueta para gerar o arquivo PDF.")

    except Exception as e:
        st.error(f"Erro ao processar o arquivo XML: {e}")