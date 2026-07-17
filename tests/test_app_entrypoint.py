from __future__ import annotations

import unittest
from importlib.resources import files
from pathlib import Path


class FastAPIEntrypointTest(unittest.TestCase):
    def test_app_entrypoint_imports_when_fastapi_is_installed(self) -> None:
        try:
            from v2.main import app
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("fastapi is not installed in this local environment")
            raise

        paths = set(app.openapi()["paths"])
        self.assertEqual(app.title, "CourseBee")
        self.assertEqual(app.version, "2.1.0")
        self.assertIn("/health", paths)
        self.assertIn("/ready", paths)
        self.assertIn("/v2/documents/ingest", paths)
        self.assertIn("/v2/ask", paths)
        self.assertIn("/v2/study-kit", paths)
        self.assertIn("/v2/audio-script", paths)
        self.assertIn("/v2/concept-map", paths)
        self.assertIn("/v2/course-packs/ask/stream", paths)

    def test_demo_uses_packaged_assets_and_api_backed_sources(self) -> None:
        package_root = files("v2")
        demo_html = package_root.joinpath("assets", "coursebee_demo_ui.html").read_text(encoding="utf-8")
        fixture_dir = package_root.joinpath("assets", "demo_fixtures")

        self.assertIn("bootstrapDemo()", demo_html)
        self.assertIn('api("/course-packs/ask"', demo_html)
        self.assertIn('id="retrievalMode"', demo_html)
        self.assertIn('value="semantic_rerank"', demo_html)
        self.assertIn("retrievalDetailsHtml(payload)", demo_html)
        self.assertIn('CHAT_LLM_PROVIDER = "ollama"', demo_html)
        self.assertIn('CHAT_LLM_MODEL = "qwen3:14b"', demo_html)
        self.assertIn("llm_provider: CHAT_LLM_PROVIDER", demo_html)
        self.assertIn("llm_model: CHAT_LLM_MODEL", demo_html)
        self.assertIn("target_chars: 2000", demo_html)
        self.assertIn('guest_voice: "ko-KR-InJoonNeural"', demo_html)
        self.assertIn("addAudioArtifact(data, true)", demo_html)
        self.assertIn('data-action="audio"', demo_html)
        self.assertIn("<b>AI 오디오 오버뷰</b>", demo_html)
        self.assertIn('const ENABLED_STUDIO_ACTIONS = new Set(["audio"])', demo_html)
        self.assertIn("configureStudioActions()", demo_html)
        self.assertIn("button.hidden = !ENABLED_STUDIO_ACTIONS.has", demo_html)
        self.assertIn(".filter((item) => ENABLED_STUDIO_ACTIONS.has(item.action))", demo_html)
        self.assertIn("!ENABLED_STUDIO_ACTIONS.has(action)", demo_html)
        self.assertIn("const STUDIO_ACTION_STATUS = Object.freeze", demo_html)
        self.assertIn("addMindmapArtifact(mindmap, exported, true)", demo_html)
        self.assertIn("addStudioArtifact(reportArtifact(", demo_html)
        self.assertIn("addStudioArtifact(flashcardArtifact(", demo_html)
        self.assertIn("addStudioArtifact(quizArtifact(", demo_html)
        self.assertIn("addStudioArtifact(tableArtifact(pack, artifacts), true)", demo_html)
        self.assertIn('[data-flashcard-flip]', demo_html)
        self.assertIn('[data-quiz-reveal]', demo_html)
        self.assertIn('.studio-card[data-action], .artifact[data-action]', demo_html)
        self.assertIn("&include_content=false", demo_html)
        self.assertIn('{ key: "audio_overview", action: "audio"', demo_html)
        self.assertIn('artifacts[item.key]?.ready', demo_html)
        self.assertIn("answerScopeHtml(payload)", demo_html)
        self.assertIn("formatAnswerText", demo_html)
        self.assertIn("formatAnswerMarkdown", demo_html)
        self.assertIn("conversation_history: history", demo_html)
        self.assertIn("/course-packs/ask/stream", demo_html)
        self.assertIn("stopAnswer.addEventListener", demo_html)
        self.assertIn("data-source-group", demo_html)
        self.assertIn('id="externalSearch"', demo_html)
        self.assertIn("allow_web_fallback", demo_html)
        self.assertIn('web_provider: "wikipedia"', demo_html)
        self.assertIn('form.append("pack_id", PACK_ID)', demo_html)
        self.assertIn('form.append("append", "true")', demo_html)
        self.assertIn("restoreActivePack()", demo_html)
        self.assertIn("coursebee.activePackId", demo_html)
        self.assertIn("외부 검색으로 확인됨", demo_html)
        self.assertIn('id="sourceOpenUrl"', demo_html)
        self.assertIn("일반지식 보충", demo_html)
        self.assertIn("현재 자료에서 답을 찾지 못했어요.", demo_html)
        self.assertIn("payload.warnings || []", demo_html)
        self.assertIn(":root{--bg:", demo_html)
        self.assertIn(".layout{", demo_html)
        self.assertIn('class="panel sources-panel"', demo_html)
        self.assertIn(".sources-panel .sources{min-height:0;overflow-y:auto}", demo_html)
        self.assertIn("height:100dvh", demo_html)
        self.assertNotIn("NLP_week11_lecture1.pptx", demo_html)
        self.assertNotIn("req_ab12c3d4", demo_html)
        self.assertEqual(len(list(fixture_dir.iterdir())), 3)

    def test_semantic_docker_profile_uses_cpu_only_torch(self) -> None:
        dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("COURSEBEE_TORCH_VERSION=", dockerfile)
        self.assertIn("https://download.pytorch.org/whl/cpu", dockerfile)


if __name__ == "__main__":
    unittest.main()


