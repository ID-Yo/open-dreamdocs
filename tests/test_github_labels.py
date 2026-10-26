import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / 'templates/task-state-labels.json'
LEGACY_PATH = ROOT / 'templates/github-labels.json'

HEX_COLOR = re.compile(r'^[0-9A-Fa-f]{6}$')

EXPECTED_LABELS = {
    'state:ready': ('BFD4F2', 'Start approved and ready; check dependencies before dispatch'),
    'state:active': ('0E8A16', 'Approved work actually in progress with a started executor'),
    'state:review': ('FBCA04', 'Candidate under independent review or QA'),
    'state:blocked': ('B60205', 'Blocked on a technical, dependency or capacity condition recorded in the issue'),
    'state:needs-owner': ('D93F0B', 'Blocked: waits on the owner; reason, resume condition and next check recorded in the issue'),
    'state:backlog': ('EDEDED', 'Recorded but not approved or scheduled; no execution expectation'),
    'future': ('C5DEF5', 'Not scheduled; no execution expectation'),
}

class GitHubLabelsTests(unittest.TestCase):
    def test_task_state_labels_template_matches_specification(self):
        self.assertTrue(TEMPLATE_PATH.is_file(), f'missing {TEMPLATE_PATH}')
        data = json.loads(TEMPLATE_PATH.read_text(encoding='utf-8'))
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), len(EXPECTED_LABELS))
        names = set()
        for item in data:
            self.assertEqual(set(item.keys()), {'name', 'color', 'description'})
            name = item['name']
            self.assertIn(name, EXPECTED_LABELS)
            self.assertNotIn(name, names, f'duplicate label name {name}')
            names.add(name)
            expected_color, expected_desc = EXPECTED_LABELS[name]
            self.assertEqual(item['color'].upper(), expected_color.upper())
            self.assertEqual(item['description'], expected_desc)
            self.assertTrue(HEX_COLOR.match(item['color']), f'invalid hex color in {item}')
            self.assertLessEqual(len(item['description']), 100, f'description exceeds 100 chars: {item}')
            self.assertGreater(len(item['description']), 0)

    def test_legacy_github_labels_template_remains_valid(self):
        self.assertTrue(LEGACY_PATH.is_file())
        data = json.loads(LEGACY_PATH.read_text(encoding='utf-8'))
        self.assertIsInstance(data, list)
        for item in data:
            self.assertTrue(HEX_COLOR.match(item['color']))
            self.assertLessEqual(len(item['description']), 100)

    def test_idempotent_creation_simulation_creates_exact_set_and_changes_nothing_on_rerun(self):
        self.assertTrue(TEMPLATE_PATH.is_file(), f'missing {TEMPLATE_PATH}')
        data = json.loads(TEMPLATE_PATH.read_text(encoding='utf-8'))
        mock_repo = {}
        def apply_labels(labels):
            created = 0
            for label in labels:
                name = label['name']
                if name not in mock_repo:
                    mock_repo[name] = {'color': label['color'], 'description': label['description']}
                    created += 1
            return created

        first_run_created = apply_labels(data)
        self.assertEqual(first_run_created, len(EXPECTED_LABELS))
        self.assertEqual(set(mock_repo.keys()), set(EXPECTED_LABELS.keys()))
        rerun_creates = [l['name'] for l in data if l['name'] not in mock_repo]
        self.assertEqual(rerun_creates, [])

if __name__ == '__main__':
    unittest.main()
