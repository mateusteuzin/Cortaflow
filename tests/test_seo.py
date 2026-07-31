import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


STATIC = Path(__file__).parents[1] / "app" / "static"
OFFICIAL_URL = "https://cortaflow.com.br/"


class LandingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.in_json_ld = False
        self.title = ""
        self.json_ld = ""
        self.metas = {}
        self.links = {}
        self.visible_text = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "script" and values.get("type") == "application/ld+json":
            self.in_json_ld = True
        if tag == "meta":
            key = values.get("name") or values.get("property")
            if key:
                self.metas[key] = values.get("content", "")
        if tag == "link" and values.get("rel"):
            self.links[values["rel"]] = values.get("href", "")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.in_json_ld:
            self.in_json_ld = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif self.in_json_ld:
            self.json_ld += data
        elif data.strip():
            self.visible_text.append(data.strip())


class TechnicalSeoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (STATIC / "preview-design.html").read_text(encoding="utf-8")
        cls.parser = LandingParser()
        cls.parser.feed(cls.html)
        cls.structured = json.loads(cls.parser.json_ld)
        cls.entities = {
            item["@type"]: item for item in cls.structured["@graph"]
        }

    def test_primary_metadata_is_complete_and_consistent(self):
        expected_title = "CortaFlow: Agenda Online e Gestão para Barbearias"
        self.assertEqual(self.parser.title.strip(), expected_title)
        self.assertEqual(self.parser.links["canonical"], OFFICIAL_URL)
        for key in (
            "description", "og:site_name", "og:title", "og:description",
            "og:image", "twitter:title", "twitter:description", "twitter:image",
        ):
            self.assertTrue(self.parser.metas.get(key), key)
        self.assertEqual(self.parser.metas["og:title"], expected_title)
        self.assertEqual(self.parser.metas["twitter:title"], expected_title)

    def test_json_ld_describes_organization_software_and_website(self):
        self.assertEqual(
            set(self.entities), {"Organization", "SoftwareApplication", "WebSite"}
        )
        organization = self.entities["Organization"]
        software = self.entities["SoftwareApplication"]
        website = self.entities["WebSite"]
        self.assertEqual(organization["email"], "suporte@cortaflow.com.br")
        self.assertEqual(organization["areaServed"]["name"], "Brasil")
        self.assertNotIn("sameAs", organization)
        self.assertEqual(software["applicationCategory"], "BusinessApplication")
        for platform in ("Web", "Android", "iOS"):
            self.assertIn(platform, software["operatingSystem"])
        self.assertEqual(software["countriesSupported"], "BR")
        self.assertEqual(software["inLanguage"], "pt-BR")
        self.assertEqual(website["inLanguage"], "pt-BR")
        self.assertEqual(website["url"], OFFICIAL_URL)

    def test_structured_logo_and_social_images_exist_in_public_assets(self):
        urls = [
            self.entities["Organization"]["logo"]["url"],
            self.parser.metas["og:image"],
            self.parser.metas["twitter:image"],
        ]
        for url in urls:
            parsed = urlparse(url)
            self.assertEqual(f"{parsed.scheme}://{parsed.netloc}/", OFFICIAL_URL)
            self.assertTrue((STATIC / parsed.path.lstrip("/")).is_file(), url)

    def test_visible_page_defines_cortaflow(self):
        visible = " ".join(self.parser.visible_text)
        self.assertIn("O que é o CortaFlow?", visible)
        self.assertIn(
            "O CortaFlow é um sistema brasileiro de agenda online e gestão para barbearias. "
            "A plataforma reúne agendamentos, profissionais, clientes, serviços, comissões, "
            "confirmações e controle financeiro.",
            visible,
        )


if __name__ == "__main__":
    unittest.main()
