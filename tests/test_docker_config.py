import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class DockerConfigTest(unittest.TestCase):
    def test_dockerfile_runs_chat_ui_on_container_host(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("FROM python:3.11-slim", dockerfile)
        self.assertIn("COPY requirements.txt", dockerfile)
        self.assertIn("pip install --no-cache-dir -r requirements.txt", dockerfile)
        self.assertIn("GRADIO_SERVER_NAME=0.0.0.0", dockerfile)
        self.assertIn("EXPOSE 7861", dockerfile)
        self.assertIn('CMD ["python", "chat_ui.py"]', dockerfile)

    def test_compose_publishes_port_and_persists_runtime_data(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("content-agent:", compose)
        self.assertIn('"7861:7861"', compose)
        self.assertIn("env_file:", compose)
        self.assertIn("./output:/app/output", compose)
        self.assertIn("./data:/app/data", compose)
        self.assertIn(".content_agent:/root/.content_agent", compose)

    def test_dockerignore_excludes_local_and_generated_files(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

        for pattern in [".git", ".venv", ".env", "output", "data", "__pycache__", "*.pyc"]:
            self.assertIn(pattern, dockerignore)


if __name__ == "__main__":
    unittest.main()
