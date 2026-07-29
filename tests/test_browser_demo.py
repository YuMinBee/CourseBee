from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen

try:
    from playwright.sync_api import Error as PlaywrightError, sync_playwright
except ModuleNotFoundError:  # pragma: no cover - exercised in the browser CI job
    PlaywrightError = RuntimeError
    sync_playwright = None


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(sync_playwright is None, "playwright is not installed")
class CourseBeeBrowserWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = tempfile.TemporaryDirectory(prefix="coursebee-browser-")
        cls.data_root = Path(cls.runtime.name) / "outputs"
        cls.port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        env = os.environ.copy()
        env["COURSEBEE_DATA_ROOT"] = str(cls.data_root)
        env["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
        cls.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "v2.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_for_server(cls.base_url, cls.server)
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            cls._close_runtime()
            raise unittest.SkipTest(f"Chromium is not installed: {exc}") from exc
        except Exception:
            cls._close_runtime()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()
        cls._close_runtime()

    @classmethod
    def _close_runtime(cls) -> None:
        server = getattr(cls, "server", None)
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        runtime = getattr(cls, "runtime", None)
        if runtime:
            runtime.cleanup()

    def _new_page(self, width: int, height: int):
        context = self.browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        page.route("**/v3/**", self._route_api_request)
        return context, page

    def _route_api_request(self, route, request) -> None:
        parsed = urlsplit(request.url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if "output_root" in query:
            query["output_root"] = str(self.data_root)
        url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))

        post_data = None
        if request.method == "POST" and "application/json" in request.headers.get("content-type", ""):
            payload = request.post_data_json
            if "output_root" in payload:
                payload["output_root"] = str(self.data_root)
            if parsed.path.endswith("/course-packs/ask/stream"):
                payload.update({"llm_provider": "mock", "llm_model": None, "allow_web_fallback": False})
            if parsed.path.endswith("/course-packs/onboarding-report"):
                payload.update({"llm_provider": "mock", "llm_model": None})
            post_data = json.dumps(payload, ensure_ascii=False)
        route.continue_(url=url, post_data=post_data)

    def test_desktop_rag_and_pptx_upload_workflow(self) -> None:
        context, page = self._new_page(1440, 900)
        page_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        try:
            page.goto(f"{self.base_url}/demo", wait_until="domcontentloaded")
            page.locator("#sourceList .src").first.wait_for(timeout=15_000)
            page.wait_for_function(
                "() => document.querySelectorAll('#sourceList .src').length === 3",
                timeout=15_000,
            )
            self.assertEqual(page.locator("#sourceList .src").count(), 3)
            self.assertGreaterEqual(int(page.locator("#sourceCount").inner_text().split()[0]), 6)
            self.assertEqual(page.locator(".studio-card:visible").count(), 2)
            self.assertEqual(page.locator(".select-line, .check, .artifact-menu").count(), 0)
            self.assertNotEqual(page.evaluate("getComputedStyle(document.body).backgroundColor"), "rgba(0, 0, 0, 0)")
            self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.sources')).overflowY"), "auto")

            source_name = page.locator("#sourceList .src b").first.inner_text()
            self.assertTrue(source_name.startswith("CourseBee Labs"))
            page.locator("#sourceList .src").first.click()
            page.locator("#sourceModal").wait_for(state="visible")
            self.assertEqual(page.locator("#sourceHeading").inner_text(), source_name)
            page.locator("#closeSource").click()

            page.locator("#questionInput").fill("업무 계정의 다중 요소 인증 규정은 무엇이야?")
            page.locator("#sendQuestion").click()
            page.locator(".assistant-scope .scope-badge").last.wait_for(timeout=20_000)
            answer = page.locator(".assistant-body").last.inner_text()
            self.assertTrue("인증" in answer or "계정" in answer)
            self.assertNotIn("자료를 검색하고 있어요", answer)

            page.locator("#briefingAudience").select_option("engineering")
            self.assertIn("배포", page.locator("#briefingObjective").inner_text())
            page.locator('.studio-card[data-action="report"]').click()
            page.locator("#studioArtifactViewer").wait_for(state="visible", timeout=20_000)
            self.assertEqual(page.locator("#studioArtifactTitle").inner_text(), "개발팀 신규 합류자 온보딩 보고서")
            self.assertIn("개발팀 신규 합류자", page.locator("#studioArtifactBody").inner_text())
            self.assertIn("근거별 브리핑", page.locator("#studioArtifactBody").inner_text())
            self.assertEqual(page.locator(".studio-report-open").count(), 1)
            with page.expect_popup() as report_popup:
                page.locator(".studio-report-open").click()
            report_page = report_popup.value
            report_page.wait_for_load_state("domcontentloaded")
            self.assertEqual(report_page.locator("h1").inner_text(), "개발팀 신규 합류자 온보딩 보고서")
            report_sources = "\n".join(report_page.locator(".sources li").all_inner_texts())
            self.assertIn("enterprise_engineering_workflow.txt", report_sources)
            self.assertIn("enterprise_security_policy.txt", report_sources)
            self.assertNotIn("enterprise_employee_handbook.txt", report_sources)
            self.assertIn("선택 문서 2/3", report_page.locator(".quality").inner_text())
            self.assertLessEqual(
                report_page.evaluate("document.documentElement.scrollWidth"),
                report_page.evaluate("window.innerWidth") + 1,
            )
            report_capture_path = os.environ.get("COURSEBEE_CAPTURE_REPORT_PATH")
            if report_capture_path:
                report_target = Path(report_capture_path)
                report_target.parent.mkdir(parents=True, exist_ok=True)
                report_page.screenshot(path=str(report_target), full_page=True)
            report_page.close()

            capture_path = os.environ.get("COURSEBEE_CAPTURE_DEMO_PATH")
            if capture_path:
                target = Path(capture_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                page.locator("#chatBody").evaluate("node => { node.scrollTop = 0; }")
                page.screenshot(path=str(target), full_page=False)
            page.locator("#studioArtifactClose").click()

            initial_count = page.locator("#sourceList .src").count()
            page.locator("#fileInput").set_input_files(
                {
                    "name": "e2e-engineering-release-update.pptx",
                    "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "buffer": _sample_pptx_bytes(),
                }
            )
            page.wait_for_function(
                "expected => document.querySelectorAll('#sourceList .src').length > expected",
                arg=initial_count,
                timeout=30_000,
            )
            pptx_icon = page.locator("#sourceList .fileicon.pptx").last
            self.assertEqual(pptx_icon.inner_text(), "PPT")

            stale_report = page.locator('#artifactList .artifact[data-action="report"]')
            stale_report.wait_for(timeout=20_000)
            page.wait_for_function(
                """() => document.querySelector('#artifactList .artifact[data-action="report"]')
                    ?.textContent.includes('자료 변경 1건')""",
                timeout=20_000,
            )
            self.assertIn("재생성 필요", stale_report.inner_text())

            stale_report.click()
            page.locator("#studioArtifactViewer").wait_for(state="visible", timeout=20_000)
            page.wait_for_function(
                "() => document.querySelector('#studioArtifactBody')?.textContent.includes('변경분 갱신')",
                timeout=20_000,
            )
            regenerated = page.locator("#studioArtifactBody").inner_text()
            self.assertIn("재사용 2개", regenerated)
            self.assertIn("재생성 1개", regenerated)
            self.assertEqual(page_errors, [])
        finally:
            context.close()

    def test_mobile_layout_has_no_horizontal_overflow(self) -> None:
        context, page = self._new_page(390, 844)
        try:
            page.goto(f"{self.base_url}/demo", wait_until="domcontentloaded")
            page.locator("#sourceList .src").first.wait_for(timeout=15_000)
            page.locator("#artifactList .artifact").first.wait_for(timeout=15_000)
            dimensions = page.evaluate(
                """() => ({
                    innerWidth: window.innerWidth,
                    scrollWidth: document.documentElement.scrollWidth,
                    panelWidths: [...document.querySelectorAll('.panel')].map(node => node.getBoundingClientRect().width)
                })"""
            )
            self.assertLessEqual(dimensions["scrollWidth"], dimensions["innerWidth"] + 1)
            self.assertTrue(
                all(width <= dimensions["innerWidth"] for width in dimensions["panelWidths"]),
                dimensions,
            )

            capture_path = os.environ.get("COURSEBEE_CAPTURE_MOBILE_PATH")
            if capture_path:
                page.locator('#artifactList .artifact[data-action="report"]').wait_for(timeout=15_000)
                target = Path(capture_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(target), full_page=True)
        finally:
            context.close()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(base_url: str, server: subprocess.Popen[str]) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        if server.poll() is not None:
            output = server.stdout.read() if server.stdout else ""
            raise RuntimeError(f"CourseBee test server exited early:\n{output}")
        try:
            with urlopen(f"{base_url}/health", timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("CourseBee test server did not become ready")


def _sample_pptx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "ppt/presentation.xml",
            '<?xml version="1.0" encoding="UTF-8"?><p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="257" r:id="rId1"/></p:sldIdLst></p:presentation>',
        )
        archive.writestr(
            "ppt/_rels/presentation.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>',
        )
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<?xml version="1.0" encoding="UTF-8"?><p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>개발팀 배포 절차 업데이트: CI 검증과 롤백 계획을 문서화한다.</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
        )
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
