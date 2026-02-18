import unittest
import os
import json
from unittest.mock import patch

# Add project root to path
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Only attempt to import if llama-cpp is mockable or we test logic around it
# Since we don't want to actually load a 5GB model in a CI/Test env, we mock the Llama class.
from engine.ai_brain import AIBrain

class TestAIIntegration(unittest.TestCase):
    def setUp(self):
        self.brain = AIBrain()

    def test_generation_logic(self):
        # Mock the model query to return valid JSON.
        expected_json = {
            "subject": "Test Subject",
            "body": "<html><body>Test Body</body></html>"
        }
        with patch.object(self.brain, "_query_model", return_value=json.dumps(expected_json)):
            # Simulate "loaded" so generate_email_campaign doesn't call load_model().
            self.brain.llm = object()

            result = self.brain.generate_email_campaign("SEO", "Dentists", "Friendly")

        self.assertEqual(result['subject'], "Test Subject")
        self.assertIn("<html>", result['body'])

    @patch('engine.ai_brain.hf_hub_download')
    def test_download_trigger(self, mock_dl):
        brain = AIBrain(
            {
                "source": "HuggingFace",
                "hf_repo_id": "some/repo",
                "hf_filename": "model.gguf",
            }
        )
        brain.download_model()
        mock_dl.assert_called_once()
        args = mock_dl.call_args[1]
        self.assertEqual(args["repo_id"], "some/repo")
        self.assertEqual(args["filename"], "model.gguf")

if __name__ == '__main__':
    unittest.main()
