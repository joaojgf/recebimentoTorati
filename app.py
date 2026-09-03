import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
import io
import re
from datetime import datetime

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(page_title="Torati Gestão Logística - Recebimento", layout="wide")
st.title("🏷️ Torati Gestão Logística - Recebimento")

# --- BARRA LATERAL: Configuração da Impressora (Padrão 60x40mm) ---
st.sidebar.header("⚙️ Configuração da Etiqueta")
largura_mm = st.sidebar.number_input("Largura (mm)", value=60, min_value=20, max_value=200)
altura_mm = st.sidebar.number_input("Altura (mm)", value=40, min_value=15, max_value=200)

def limpar_sku(sku_raw):
    """Remove colchetes, espaços e caracteres especiais para gerar código de barras limpo"""
    if not sku_raw:
        return ""
    return re.sub(r'[^a-zA-Z0-9\-]', '', str(sku_raw)).strip()

def formatar_data(data_raw):
    """Converte datas AAAA-MM-DD para DD/MM/AAAA"""
    if not data_raw or data_raw == "N/I":
        return "N/I"
    try:
        data_limpa = data_raw.split('T')[0]
        return datetime.strptime(data_limpa, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return data_raw

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
        fontSize=9.5,
        leading=11,
        spaceAfter=1
    )
    
    estilo_desc = ParagraphStyle(
        'Desc_Style',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=8.5
    )

    estilo_lote_val = ParagraphStyle(
        'Lote_Val_Style',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=8.5
    )

    for item in produtos_com_qtd:
        sku_original = str(item['SKU'])
        sku_limpo = limpar_sku(sku_original)
        descricao = str(item['Descrição do Produto'])
        lote = str(item['Lote'])
        validade = str(item['Validade'])
        qtd_imprimir = int(item['Quantidade de Etiquetas'])

        for _ in range(qtd_imprimir):
            margem_x = 3 * mm
            margem_topo = 2.5 * mm
            margem_fundo = 2.5 * mm
            largura_util = largura_pt - (2 * margem_x)

            # 1. Desenha o SKU Limpo no topo
            p_sku = Paragraph(f"<b>SKU: {sku_limpo}</b>", estilo_sku)
            w_sku, h_sku = p_sku.wrap(largura_util, altura_pt)
            y_atual = altura_pt - margem_topo - h_sku
            p_sku.drawOn(c, margem_x, y_atual)

            # 2. Desenha a Descrição
            p_desc = Paragraph(descricao, estilo_desc)
            w_desc, h_desc = p_desc.wrap(largura_util, y_atual)
            y_atual -= (h_desc + 1 * mm)
            p_desc.drawOn(c, margem_x, y_atual)

            # 3. Desenha Lote e Validade
            texto_lote_val = f"LOTE: {lote} | VAL: {validade}"
            p_lv = Paragraph(texto_lote_val, estilo_lote_val)
            w_lv, h_lv = p_lv.wrap(largura_util, y_atual)
            y_atual -= (h_lv + 1 * mm)
            p_lv.drawOn(c, margem_x, y_atual)

            # 4. Código de Barras Ajustado
            espaco_disponivel = y_atual - margem_fundo - (3.5 * mm)
            altura_barras = min(12 * mm, max(7 * mm, espaco_disponivel))
            
            tam_sku = max(len(sku_limpo), 4)
            largura_unidade_barra = min(0.38 * mm, largura_util / (tam_sku * 11 + 35))
            
            bc = code128.Code128(
                sku_limpo, 
                barHeight=altura_barras, 
                barWidth=largura_unidade_barra,
                humanReadable=False
            )
            
            pos_y_barras = margem_fundo + (3 * mm)
            pos_x_barras = (largura_pt - bc.width) / 2
            pos_x_barras = max(margem_x, pos_x_barras)
            
            bc.drawOn(c, pos_x_barras, pos_y_barras)

            # 5. Texto legível do SKU abaixo da barra
            c.setFont("Helvetica", 7)
            c.drawCentredString(largura_pt / 2, margem_fundo, sku_limpo)

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

        # 1. Extração dos Dados Principais
        n_nf = root.find('.//nfe:ide/nfe:nNF', ns)
        numero_nota = n_nf.text if n_nf is not None else "N/A"

        emit = root.find('.//nfe:emit/nfe:xNome', ns)
        emitente = emit.text if emit is not None else "N/A"

        dest = root.find('.//nfe:dest/nfe:xNome', ns)
        destinatario = dest.text if dest is not None else "N/A"

        # Data de Emissão
        dh_emi = root.find('.//nfe:ide/nfe:dhEmi', ns)
        if dh_emi is None:
            dh_emi = root.find('.//nfe:ide/nfe:dEmi', ns)
        
        data_emissao = formatar_data(dh_emi.text if dh_emi is not None else "N/I")

        # Quantidade de Volumes
        q_vol = root.find('.//nfe:transp/nfe:vol/nfe:qVol', ns)
        volumes = q_vol.text if q_vol is not None else "1"

        st.success(f"Nota Fiscal **{numero_nota}** recebida com sucesso!")
        
        # Exibição dos dados principais
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

        # 2. Mensagem para o WhatsApp
        st.subheader("💬 Mensagem para o WhatsApp")
        mensagem_whatsapp = (
            f"Acusamos o recebimento da(s) seguinte(s) NF(s): {numero_nota} de {data_emissao}\n\n"
            f"Destinatário: {destinatario}\n"
            f"Fornecedor: {emitente}\n"
            f"VOLUMES: {volumes}"
        )
        st.code(mensagem_whatsapp, language=None)

        st.divider()

        # 3. Extração dos Produtos com Lote e Validade
        produtos = []
        for det in root.findall('.//nfe:det', ns):
            sku = det.find('.//nfe:prod/nfe:cProd', ns)
            descricao = det.find('.//nfe:prod/nfe:xProd', ns)
            quantidade = det.find('.//nfe:prod/nfe:qCom', ns)

            # Busca informações de Lote e Validade (tags <rastro> ou <med>)
            lote_elem = det.find('.//nfe:prod/nfe:rastro/nfe:nLote', ns)
            val_elem = det.find('.//nfe:prod/nfe:rastro/nfe:dVal', ns)

            if lote_elem is None:
                lote_elem = det.find('.//nfe:prod/nfe:med/nfe:nLote', ns)
            if val_elem is None:
                val_elem = det.find('.//nfe:prod/nfe:med/nfe:dVal', ns)

            lote_val = lote_elem.text if lote_elem is not None else "N/I"
            validade_val = formatar_data(val_elem.text if val_elem is not None else "N/I")

            qtd_float = float(quantidade.text) if quantidade is not None else 1.0

            produtos.append({
                "SKU": sku.text if sku is not None else "N/A",
                "Descrição do Produto": descricao.text if descricao is not None else "N/A",
                "Lote": lote_val,
                "Validade": validade_val,
                "Qtd. Nota Fiscal": int(qtd_float)
            })

        # 4. Ajuste Manual da Quantidade de Etiquetas a Imprimir
        st.subheader("📦 Seleção e Ajuste de Etiquetas para Impressão")
        st.info("Abaixo você pode alterar manualmente a quantidade de etiquetas que deseja imprimir para cada produto.")

        produtos_para_impressao = []
        
        for idx, item in enumerate(produtos):
            col_info, col_qtd = st.columns([3, 1])
            with col_info:
                st.write(f"**SKU:** {limpar_sku(item['SKU'])} | **Item:** {item['Descrição do Produto']}")
                st.caption(f"Lote: {item['Lote']} | Validade: {item['Validade']} | Qtd. na Nota: {item['Qtd. Nota Fiscal']}")
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
                    "Lote": item["Lote"],
                    "Validade": item["Validade"],
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
