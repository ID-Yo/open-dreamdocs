import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / 'templates/task-state-labels.json'
GENERAL_PATH = ROOT / 'templates/github-labels.json'

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

    def test_general_labels_template_has_only_approved_types_and_priority(self):
        data = json.loads(GENERAL_PATH.read_text(encoding='utf-8'))
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 4)
        self.assertEqual({item['name'] for item in data},
                         {'type:epic', 'type:story', 'type:task', 'priority:high'})
        for item in data:
            self.assertEqual(set(item), {'name', 'color', 'description'})
            self.assertTrue(HEX_COLOR.match(item['color']))
            self.assertTrue(item['description'])
            self.assertLessEqual(len(item['description']), 100)

    def test_templates_have_exactly_11_unique_approved_names_without_overlap(self):
        state = json.loads(TEMPLATE_PATH.read_text(encoding='utf-8'))
        general = json.loads(GENERAL_PATH.read_text(encoding='utf-8'))
        state_names = {item['name'] for item in state}
        general_names = {item['name'] for item in general}
        names = [item['name'] for item in state + general]
        self.assertFalse(state_names & general_names)
        self.assertEqual(len(names), 11)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(EXPECTED_LABELS) |
                         {'type:epic', 'type:story', 'type:task', 'priority:high'})

    def test_idempotent_creation_simulation_creates_exact_set_and_changes_nothing_on_rerun(self):
        self.assertTrue(TEMPLATE_PATH.is_file(), f'missing {TEMPLATE_PATH}')
        data = json.loads(TEMPLATE_PATH.read_text(encoding='utf-8'))
        mock_repo = {}
        def apply_labels(labels, force=True):
            created = 0
            overwritten = 0
            for label in labels:
                name = label['name']
                if name not in mock_repo:
                    mock_repo[name] = {'color': label['color'], 'description': label['description']}
                    created += 1
                elif force:
                    # --force overwrites color and description
                    if mock_repo[name] != {'color': label['color'], 'description': label['description']}:
                        mock_repo[name] = {'color': label['color'], 'description': label['description']}
                        overwritten += 1
            return created, overwritten

        first_run_created, _ = apply_labels(data)
        self.assertEqual(first_run_created, len(EXPECTED_LABELS))
        self.assertEqual(set(mock_repo.keys()), set(EXPECTED_LABELS.keys()))
        # Re-run changes nothing
        rerun_created, rerun_overwritten = apply_labels(data, force=True)
        self.assertEqual(rerun_created, 0)
        self.assertEqual(rerun_overwritten, 0)

        # Collision with differing metadata: --force explicitly overwrites
        mock_repo['state:ready'] = {'color': '000000', 'description': 'Custom user description'}
        c_created, c_overwritten = apply_labels(data, force=True)
        self.assertEqual(c_created, 0)
        self.assertEqual(c_overwritten, 1)
        self.assertEqual(mock_repo['state:ready']['color'], 'BFD4F2')

        # Conflict-refusing path: raises or rejects when differing
        mock_repo['state:ready'] = {'color': '000000', 'description': 'Custom user description'}
        conflicts = [
            l['name'] for l in data
            if l['name'] in mock_repo and mock_repo[l['name']] != {'color': l['color'], 'description': l['description']}
        ]
        self.assertEqual(conflicts, ['state:ready'])

if __name__ == '__main__':
    unittest.main()
