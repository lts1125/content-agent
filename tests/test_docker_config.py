import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class DockerConfigTest(unittest.TestCase):
    def test_dockerfile_runs_chat_ui_on_container_host(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("FROM python:3.11-slim", dockerfile)
        self.assertIn("ARG REQUIREMENTS_FILE=requirements-docker.txt", dockerfile)
        self.assertIn("ARG PIP_INDEX_URL=", dockerfile)
        self.assertIn("ARG USE_CHINA_APT_MIRROR=true", dockerfile)
        self.assertIn("COPY requirements.txt requirements-docker.txt", dockerfile)
        self.assertIn("pip install --no-cache-dir -i ${PIP_INDEX_URL} -r ${REQUIREMENTS_FILE}", dockerfile)
        self.assertIn("GRADIO_SERVER_NAME=0.0.0.0", dockerfile)
        self.assertIn("EXPOSE 7861", dockerfile)
        self.assertIn('CMD ["python", "chat_ui.py"]', dockerfile)

    def test_compose_publishes_port_and_persists_runtime_data(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("content-agent:", compose)
        self.assertIn("REQUIREMENTS_FILE:", compose)
        self.assertIn("PIP_INDEX_URL:", compose)
        self.assertIn("USE_CHINA_APT_MIRROR:", compose)
        self.assertIn('"7861:7861"', compose)
        self.assertIn("env_file:", compose)
        self.assertIn("./output:/app/output", compose)
        self.assertIn("./data:/app/data", compose)
        self.assertIn(".content_agent:/root/.content_agent", compose)

    def test_dockerignore_excludes_local_and_generated_files(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

        for pattern in [".git", ".venv", ".env", "output", "data", "__pycache__", "*.pyc"]:
            self.assertIn(pattern, dockerignore)

    def test_docker_requirements_excludes_rag_heavy_dependencies(self):
        docker_reqs = (ROOT / "requirements-docker.txt").read_text(encoding="utf-8")

        self.assertIn("gradio==4.44.1", docker_reqs)
        self.assertIn("huggingface-hub==0.36.2", docker_reqs)
        self.assertIn("pydantic-ai-slim[openai]==0.8.1", docker_reqs)
        self.assertIn("ddgs", docker_reqs)
        self.assertNotIn("duckduckgo-search", docker_reqs)
        self.assertNotIn("sentence-transformers", docker_reqs)
        self.assertNotIn("chromadb", docker_reqs)


if __name__ == "__main__":
    unittest.main()
