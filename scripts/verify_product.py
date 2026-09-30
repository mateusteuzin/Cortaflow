"""Real-browser product checks with synthetic data and no production services."""
import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "product-redesign"


def run():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            for width, height in [(390, 844), (768, 1024), (1440, 900)]:
                page = browser.new_page(viewport={"width": width, "height": height}, service_workers="block")
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                pending = []
                def route_request(route):
                    path = urlparse(route.request.url).path
                    if path.startswith("/agendar/"):
                        route.fulfill(path=str(ROOT / "app/static/cliente.html"), content_type="text/html")
                    elif path.startswith("/api/public/"):
                        if path.endswith("/servicos"):
                            data = [{"id": 1, "nome": "Corte masculino", "preco": 45, "duracao_minutos": 30}, {"id": 2, "nome": "Corte e barba", "preco": 70, "duracao_minutos": 60}]
                        elif path.endswith("/profissionais"):
                            data = [{"id": 1, "nome": "Leonardo"}]
                        elif path.endswith("/horarios"):
                            pending.append(route)
                            return
                        elif path.endswith("/agendamentos"):
                            data = {"id": 42}
                        else:
                            data = {"nome": "Barbearia Central", "endereco": "Rua Central, 100", "telefone": "11999999999"}
                        route.fulfill(body=json.dumps(data), content_type="application/json")
                    else:
                        relative = path.lstrip("/")
                        file = ROOT / "app/static" / relative
                        if file.is_file():
                            route.fulfill(path=str(file))
                        else:
                            route.continue_()
                page.route(base + "/**", route_request)
                page.goto(base + "/agendar/central")
                page.locator(".service-option").first.click()
                page.locator(".professional").first.click()
                page.wait_for_timeout(50)
                page.locator(".service-option").nth(1).click()
                page.wait_for_timeout(50)
                assert len(pending) == 2, "Two availability requests expected"
                pending[1].fulfill(json={"horarios": ["14:00"]})
                page.wait_for_timeout(50)
                pending[0].fulfill(json={"horarios": ["09:00"]})
                page.wait_for_timeout(100)
                assert page.locator(".slot").first.inner_text() == "14:00", "Stale availability overwrote current service"
                page.screenshot(path=str(ARTIFACTS / f"booking-{width}.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Booking overflow at {width}"
                page.locator(".slot").first.click()
                assert page.locator(".slot").first.get_attribute("aria-pressed") == "true"
                page.click("#to-details")
                page.fill("#name", "Cliente de teste")
                page.fill("#phone", "11999999999")
                page.fill("#client-email", "teste@example.com")
                page.click("#to-review")
                page.click("#confirm")
                page.locator("#success:not(.hidden)").wait_for()
                assert "#0042" in page.locator("#summary").inner_text()
                assert not errors, errors
                page.close()
            print("PASS: booking race, selection, review and confirmation at 390, 768, 1440px")
            for width, height in [(390, 844), (768, 1024), (1440, 900)]:
                page = browser.new_page(viewport={"width": width, "height": height}, service_workers="block")
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.add_init_script("localStorage.setItem('token','synthetic-test'); localStorage.setItem('name','Leonardo'); localStorage.setItem('cortaflow-theme','light');")
                def panel_route(route):
                    path = urlparse(route.request.url).path
                    if path.startswith("/api/"):
                        if path == "/api/auth/contexto":
                            data = {"perfil": "administrador", "nome": "Leonardo", "barbearia_id": 1}
                        elif path == "/api/billing/subscription":
                            data = {"active": True, "plan": "premium", "features": ["relatorios", "financeiro", "exportacoes"]}
                        elif path == "/api/barbearia/perfil":
                            data = {"nome": "Barbearia Central", "slug": "central", "telefone": "11999999999", "email_notificacoes": "teste@example.com"}
                        elif path == "/api/barbearia/barbeiros":
                            data = [{"id": 1, "nome": "Leonardo", "ativo": True, "comissao_percentual": 40}]
                        elif path == "/api/relatorios/dia":
                            data = {"total": {"total": 270, "cortes": 6}}
                        elif path == "/api/push/config":
                            data = {"enabled": False}
                        else:
                            data = []
                        route.fulfill(body=json.dumps(data), content_type="application/json")
                    else:
                        file = ROOT / "app/static" / path.lstrip("/")
                        if file.is_file():
                            route.fulfill(path=str(file))
                        else:
                            route.continue_()
                page.route(base + "/**", panel_route)
                page.goto(base + "/app/static/index.html")
                try:
                    page.locator("#revenue").filter(has_text="270").wait_for(timeout=5000)
                except Exception:
                    page.screenshot(path=str(ARTIFACTS / "panel-debug.png"), full_page=True)
                    print("Panel errors:", errors, "Toast:", page.locator("#toast").text_content())
                    raise
                for theme in ["light", "dark"]:
                    if theme == "dark":
                        page.click("#theme-toggle")
                    page.screenshot(path=str(ARTIFACTS / f"panel-{theme}-{width}.png"), full_page=True)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Panel overflow at {width}"
                if width < 821:
                    page.click("#menu")
                page.click('[data-view="agenda"]')
                page.locator("#agenda:not(.hidden)").wait_for()
                page.screenshot(path=str(ARTIFACTS / f"agenda-{width}.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Agenda overflow at {width}"
                assert not errors, errors
                page.close()
            print("PASS: panel, theme switch and agenda navigation at 390, 768, 1440px")
            for width in [390, 768, 1440]:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.route(base + "/**", lambda route: route.fulfill(path=str(ROOT / "app/static" / urlparse(route.request.url).path.lstrip("/"))) if (ROOT / "app/static" / urlparse(route.request.url).path.lstrip("/")).is_file() else route.continue_())
                page.goto(base + "/app/static/preview-design.html")
                page.screenshot(path=str(ARTIFACTS / f"landing-{width}.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Landing overflow at {width}"
                page.goto(base + "/artifacts/email-redesign/customer.html")
                page.screenshot(path=str(ARTIFACTS / f"email-{width}.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Email overflow at {width}"
                page.close()
            print("PASS: landing and email layouts at 390, 768, 1440px")
        finally:
            browser.close()
            server.shutdown()


if __name__ == "__main__":
    run()
