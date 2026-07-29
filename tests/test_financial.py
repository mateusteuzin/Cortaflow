import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from app import main
from app.services.financial_exports import build_financial_pdf, build_financial_xlsx


def sample_financial_data():
    return {
        "barbearia_nome": "BlackBarber",
        "periodo_label": "07/2026",
        "faturamento_servicos": 1500,
        "faturamento_produtos": 300,
        "faturamento_total": 1800,
        "comissoes": 600,
        "custos_produtos": 120,
        "despesas_total": 400,
        "lucro_liquido": 680,
        "margem_liquida": 37.777,
        "atendimentos": 2,
        "atendimentos_detalhes": [
            {
                "data_hora": datetime(2026, 7, 10, 10),
                "cliente_nome": "Cliente Teste",
                "servico": "Corte",
                "barbeiro_nome": "Mateus",
                "preco": Decimal("50"),
                "comissao": Decimal("20"),
            }
        ],
        "vendas_detalhes": [
            {
                "criado_em": datetime(2026, 7, 10, 11, tzinfo=timezone.utc),
                "produto_nome": "Pomada",
                "quantidade": 2,
                "preco_unitario": Decimal("30"),
                "total_venda": Decimal("60"),
                "total_custo": Decimal("24"),
            }
        ],
        "despesas": [
            {
                "data": date(2026, 7, 5),
                "descricao": "Energia",
                "categoria_label": "Energia",
                "valor": Decimal("400"),
                "recorrente": True,
                "observacao": "",
            }
        ],
    }


class FinancialCalculationTests(unittest.TestCase):
    @patch("app.main.all_rows")
    @patch("app.main.one", return_value={"nome": "BlackBarber"})
    def test_net_profit_deducts_commissions_costs_and_expenses(self, _shop, rows):
        rows.side_effect = [
            [{"preco": Decimal("1000"), "comissao": Decimal("400")}],
            [{"total_venda": Decimal("200"), "total_custo": Decimal("80")}],
            [{"valor": Decimal("300"), "categoria": "energia"}],
        ]
        result = main.financial_data(7, 7, 2026)
        self.assertEqual(result["faturamento_total"], 1200)
        self.assertEqual(result["lucro_liquido"], 420)
        self.assertEqual(result["margem_liquida"], 35)


class FinancialExportTests(unittest.TestCase):
    def test_xlsx_contains_expected_financial_sheets(self):
        content = build_financial_xlsx(sample_financial_data())
        self.assertTrue(content.startswith(b"PK"))
        with ZipFile(BytesIO(content)) as archive:
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        for name in ("Resumo", "Atendimentos", "Produtos", "Despesas"):
            self.assertIn(f'name="{name}"', workbook_xml)

    def test_pdf_is_generated_with_financial_summary(self):
        content = build_financial_pdf(sample_financial_data())
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 2000)


if __name__ == "__main__":
    unittest.main()
