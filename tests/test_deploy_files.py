import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class DeployFileTests(unittest.TestCase):
    def test_docker_compose_keeps_config_read_only_and_persists_data(self):
        compose = (REPO_ROOT / "docker-compose.yml").read_text()

        self.assertIn("./config.py:/app/config.py:ro", compose)
        self.assertIn("./data:/data", compose)

    def test_dockerignore_excludes_config_py_from_image_build_context(self):
        dockerignore = (REPO_ROOT / ".dockerignore").read_text().splitlines()

        self.assertIn("config.py", dockerignore)


if __name__ == "__main__":
    unittest.main()
