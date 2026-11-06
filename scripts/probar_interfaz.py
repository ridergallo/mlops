"""Prueba el chat en un navegador real contra la API Docker ya desplegada.

Utiliza Playwright instalado en artifacts/documentacion_dependencias y Edge.
No modifica modelos ni datos; solo envía solicitudes de inferencia.
"""
import json
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "artifacts/documentacion_dependencias"))
from playwright.sync_api import sync_playwright, expect


def main():
    salida = RAIZ / "evidencias/interfaz_chat"
    salida.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", headless=True)
        page = navegador.new_page(viewport={"width": 1440, "height": 1100})
        errores = []
        page.on("pageerror", lambda error: errores.append(str(error)))
        peticiones = []
        page.on("request", lambda req: peticiones.append(req.post_data_json) if req.url.endswith('/predecir') and req.method == 'POST' else None)
        page.goto("http://127.0.0.1:18000/", wait_until="networkidle")

        def responder(texto):
            page.locator('#mensaje').fill(texto)
            page.locator('#chat-send').click()

        responder('2026-02-30 06:00')
        expect(page.locator('.msg.bot').last).to_contain_text('fecha no es válida')
        responder('2018-01-01T06:00:00Z')
        expect(page.locator('#paso')).to_have_text('Lectura 1 / 6')
        responder('120')
        expect(page.locator('#paso')).to_have_text('Lectura 1 / 6')
        for valor in ['20,1','20.3','20.5','20.8','21','21.2']:
            responder(valor)
        expect(page.locator('#paso')).to_have_text('Revisar datos')
        assert not peticiones, 'El chat debe esperar confirmación.'
        responder('predecir')
        expect(page.locator('#paso')).to_have_text('Consulta completada', timeout=30000)
        assert peticiones[-1]['temperaturas'] == [20.1,20.3,20.5,20.8,21,21.2]
        assert peticiones[-1]['hora'] == '2018-01-01T06:00:00.000Z'
        expect(page.locator('#trazabilidad')).to_contain_text('Pod:')
        assert page.locator('#grafica circle').count() == 7
        assert page.locator('.history-item').count() == 1
        page.screenshot(path=str(salida / 'escritorio.png'), full_page=True)
        page.locator('#temp-5').fill('22')
        expect(page.locator('#explicacion')).to_contain_text('Datos modificados')
        # Error de red simulado: conservar entradas y permitir reintentar.
        page.route('**/predecir', lambda route: route.fulfill(status=503, content_type='application/json', body='{"detail":"Prueba"}'))
        page.locator('#enviar').click()
        expect(page.locator('#error')).to_contain_text('HTTP 503')
        expect(page.locator('#temp-5')).to_have_value('22')
        expect(page.locator('#enviar')).to_be_enabled()
        page.unroute('**/predecir')
        page.locator('#enviar').click()
        expect(page.locator('.history-item')).to_have_count(2, timeout=30000)
        page.locator('#reiniciar').click()
        expect(page.locator('#hora')).to_have_value('')
        expect(page.locator('#valor')).to_contain_text('—')
        page.set_viewport_size({"width":390,"height":844})
        page.locator('#ejemplo').click()
        page.locator('#enviar').click()
        expect(page.locator('#paso')).to_have_text('Consulta completada',timeout=30000)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Hay desbordamiento en móvil.'
        page.screenshot(path=str(salida/'movil.png'),full_page=True)
        assert not errores, errores
        (salida/'prueba.json').write_text(json.dumps({"estado":"correcto", "errores_javascript":errores,
            "casos":["fecha inexistente","rango inválido","coma decimal","chat paso a paso","confirmación explícita",
                     "inferencia real","gráfica","edición","error HTTP y reintento","reinicio","ejemplo","vista móvil"]},indent=2,ensure_ascii=False),encoding='utf-8')
        navegador.close()
    print('Interfaz verificada: chat, API real, errores, reintento y móvil.')


if __name__ == '__main__':
    main()
