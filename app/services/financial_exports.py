from __future__ import annotations

from datetime import datetime
from io import BytesIO

import xlsxwriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


GOLD = "#C99536"
DARK = "#171915"
MUTED = "#6F736B"
LIGHT = "#F4F1E9"
CURRENCY = 'R$ #,##0.00;[Red]-R$ #,##0.00'


def _number(value) -> float:
    return float(value or 0)


def _excel_datetime(value):
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def build_financial_xlsx(data: dict) -> bytes:
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    workbook.set_properties({
        "title": f"Relatório financeiro - {data['barbearia_nome']}",
        "company": "CortaFlow",
        "comments": "Relatório gerado pelo CortaFlow",
    })
    title = workbook.add_format({"bold": True, "font_size": 20, "font_color": "#FFFFFF", "bg_color": DARK, "align": "left", "valign": "vcenter"})
    section = workbook.add_format({"bold": True, "font_size": 11, "font_color": "#FFFFFF", "bg_color": DARK, "align": "left"})
    label = workbook.add_format({"font_color": MUTED, "bold": True, "font_size": 9})
    value = workbook.add_format({"bold": True, "font_size": 15, "num_format": CURRENCY})
    positive = workbook.add_format({"bold": True, "font_size": 15, "font_color": "#277A45", "num_format": CURRENCY})
    negative = workbook.add_format({"bold": True, "font_size": 15, "font_color": "#A13F36", "num_format": CURRENCY})
    header = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": GOLD, "border": 0, "align": "center"})
    text = workbook.add_format({"font_color": DARK})
    date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy", "align": "center"})
    money_fmt = workbook.add_format({"num_format": CURRENCY, "align": "right"})
    percent_fmt = workbook.add_format({"num_format": "0.0%", "align": "right"})

    summary = workbook.add_worksheet("Resumo")
    summary.hide_gridlines(2)
    summary.set_column("A:A", 26)
    summary.set_column("B:B", 20)
    summary.set_column("C:C", 3)
    summary.set_column("D:D", 28)
    summary.set_column("E:E", 20)
    summary.set_row(0, 34)
    summary.merge_range("A1:E1", f"{data['barbearia_nome']} - Relatório financeiro", title)
    summary.merge_range("A2:E2", data["periodo_label"], workbook.add_format({"font_color": MUTED, "italic": True}))
    cards = [
        ("Faturamento de serviços", data["faturamento_servicos"]),
        ("Vendas de produtos", data["faturamento_produtos"]),
        ("Comissões", -_number(data["comissoes"])),
        ("Custos dos produtos", -_number(data["custos_produtos"])),
        ("Despesas", -_number(data["despesas_total"])),
        ("Lucro líquido", data["lucro_liquido"]),
    ]
    for index, (name, amount) in enumerate(cards):
        row = 3 + (index // 2) * 3
        col = 0 if index % 2 == 0 else 3
        summary.write(row, col, name.upper(), label)
        cell_format = positive if name == "Lucro líquido" and _number(amount) >= 0 else negative if _number(amount) < 0 else value
        summary.write_number(row + 1, col, _number(amount), cell_format)
    summary.write("A14", "MARGEM LÍQUIDA", label)
    summary.write_number("B14", _number(data["margem_liquida"]) / 100, percent_fmt)
    summary.write("D14", "ATENDIMENTOS", label)
    summary.write_number("E14", int(data["atendimentos"]), workbook.add_format({"bold": True, "font_size": 15}))
    summary.write("A17", "COMO O LUCRO É CALCULADO", section)
    summary.merge_range("A18:E19", "Serviços + produtos - comissões - custos dos produtos - despesas. Valores sem custo cadastrado são considerados R$ 0,00.", workbook.add_format({"text_wrap": True, "valign": "top", "font_color": MUTED, "bg_color": LIGHT}))

    def add_table_sheet(name, columns, rows, widths):
        sheet = workbook.add_worksheet(name)
        sheet.hide_gridlines(2)
        sheet.freeze_panes(1, 0)
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)
        for col, column in enumerate(columns):
            sheet.write(0, col, column, header)
        for row_index, row_values in enumerate(rows, 1):
            for col_index, item in enumerate(row_values):
                fmt = text
                if isinstance(item, dict):
                    fmt = item.get("format", text)
                    item = item.get("value")
                if hasattr(item, "year") and hasattr(item, "month"):
                    sheet.write_datetime(row_index, col_index, _excel_datetime(item), date_fmt)
                elif isinstance(item, (int, float)):
                    sheet.write_number(row_index, col_index, item, fmt)
                else:
                    sheet.write(row_index, col_index, item, fmt)
        if rows:
            sheet.autofilter(0, 0, len(rows), len(columns) - 1)
        return sheet

    appointments = [
        [item["data_hora"], item["cliente_nome"], item["servico"], item["barbeiro_nome"],
         {"value": _number(item["preco"]), "format": money_fmt},
         {"value": _number(item["comissao"]), "format": money_fmt}]
        for item in data["atendimentos_detalhes"]
    ]
    add_table_sheet("Atendimentos", ["Data", "Cliente", "Serviço", "Profissional", "Valor", "Comissão"], appointments, [13, 24, 24, 22, 15, 15])

    sales = [
        [item["criado_em"], item["produto_nome"], int(item["quantidade"]),
         {"value": _number(item["preco_unitario"]), "format": money_fmt},
         {"value": _number(item["total_venda"]), "format": money_fmt},
         {"value": _number(item["total_custo"]), "format": money_fmt}]
        for item in data["vendas_detalhes"]
    ]
    add_table_sheet("Produtos", ["Data", "Produto", "Quantidade", "Preço unitário", "Total vendido", "Custo"], sales, [13, 28, 12, 17, 17, 15])

    expenses = [
        [item["data"], item["descricao"], item["categoria_label"],
         {"value": _number(item["valor"]), "format": money_fmt},
         "Sim" if item["recorrente"] else "Não", item.get("observacao") or ""]
        for item in data["despesas"]
    ]
    add_table_sheet("Despesas", ["Data", "Descrição", "Categoria", "Valor", "Recorrente", "Observação"], expenses, [13, 30, 18, 16, 13, 38])

    workbook.close()
    output.seek(0)
    return output.read()


def build_financial_pdf(data: dict) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Relatório financeiro - {data['barbearia_nome']}",
        author="CortaFlow",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("FinanceTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.HexColor(DARK), alignment=TA_CENTER, spaceAfter=5 * mm)
    subtitle = ParagraphStyle("FinanceSubtitle", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor(MUTED), alignment=TA_CENTER, spaceAfter=7 * mm)
    heading = ParagraphStyle("FinanceHeading", parent=styles["Heading2"], fontSize=14, textColor=colors.HexColor(DARK), spaceBefore=3 * mm, spaceAfter=3 * mm)
    story = [
        Paragraph(data["barbearia_nome"], title_style),
        Paragraph(f"Relatório financeiro - {data['periodo_label']}", subtitle),
    ]

    card_data = [
        ["SERVIÇOS", "PRODUTOS", "COMISSÕES", "DESPESAS", "LUCRO LÍQUIDO"],
        [
            _currency(data["faturamento_servicos"]),
            _currency(data["faturamento_produtos"]),
            _currency(data["comissoes"]),
            _currency(data["despesas_total"]),
            _currency(data["lucro_liquido"]),
        ],
    ]
    cards = Table(card_data, colWidths=[49 * mm] * 5, rowHeights=[8 * mm, 13 * mm])
    cards.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(DARK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor(LIGHT)),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor(DARK)),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 12),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#D8D4CA")),
        ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#D8D4CA")),
    ]))
    story.extend([cards, Spacer(1, 6 * mm)])
    story.append(Paragraph(
        f"Margem líquida: <b>{_number(data['margem_liquida']):.1f}%</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Atendimentos concluídos: <b>{int(data['atendimentos'])}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Custos dos produtos: <b>{_currency(data['custos_produtos'])}</b>",
        styles["Normal"],
    ))
    story.extend(_pdf_table_section("Despesas do período", ["Data", "Descrição", "Categoria", "Valor"], [
        [item["data"].strftime("%d/%m/%Y"), item["descricao"], item["categoria_label"], _currency(item["valor"])]
        for item in data["despesas"]
    ]))
    story.append(PageBreak())
    story.extend(_pdf_table_section("Atendimentos concluídos", ["Data", "Cliente", "Serviço", "Profissional", "Valor", "Comissão"], [
        [item["data_hora"].strftime("%d/%m/%Y"), item["cliente_nome"], item["servico"], item["barbeiro_nome"], _currency(item["preco"]), _currency(item["comissao"])]
        for item in data["atendimentos_detalhes"]
    ]))
    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    output.seek(0)
    return output.read()


def _pdf_table_section(title: str, headers: list[str], rows: list[list]) -> list:
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("TableHeading", parent=styles["Heading2"], fontSize=14, textColor=colors.HexColor(DARK), spaceBefore=5 * mm, spaceAfter=3 * mm)
    content = [Paragraph(title, heading)]
    if not rows:
        content.append(Paragraph("Nenhum registro neste período.", styles["Normal"]))
        return content
    table = Table([headers, *rows], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GOLD)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF8F3")]),
        ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#D8D4CA")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    content.append(table)
    return content


def _currency(value) -> str:
    return f"R$ {_number(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawString(16 * mm, 8 * mm, "CortaFlow - relatório financeiro")
    canvas.drawRightString(281 * mm, 8 * mm, f"Página {doc.page}")
    canvas.restoreState()
