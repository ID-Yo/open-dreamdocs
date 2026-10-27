"""Check that published entry points route every role to the same intake policy."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'docs/governance/task-intake.md'
ROLES = ('manager', 'developer', 'code-reviewer', 'verifier')


class TaskIntakeTests(unittest.TestCase):
    def test_root_bootstrap_and_four_roles_link_to_issue_first_policy(self):
        self.assertTrue(POLICY.is_file())
        entries = ['AGENTS.md', 'prompts/agent-bootstrap.md']
        entries += [f'templates/roles/{role}.md' for role in ROLES]
        for relative in entries:
            with self.subTest(entry=relative):
                path = ROOT / relative
                text = path.read_text(encoding='utf-8')
                self.assertIn('GitHub issue before actionable work', text)
                targets = re.findall(r'\]\(([^)#]+)', text)
                self.assertIn(POLICY, [(path.parent / target).resolve() for target in targets])

    def test_role_templates_keep_stage_and_ready_work_rules(self):
        for role in ROLES:
            with self.subTest(role=role):
                text = (ROOT / f'templates/roles/{role}.md').read_text(encoding='utf-8')
                for requirement in ('stage completion record', 'Refs #N', 'approved ready work', 'Manager'):
                    self.assertIn(requirement, text)

    def test_intake_covers_reuse_privacy_offline_and_issue_contents(self):
        text = POLICY.read_text(encoding='utf-8')
        for requirement in ('before execution starts', 'parent issue', 'Conversation and short read-only questions',
                            'pending-sync', 'stable ID', 'not published yet', 'without duplicates',
                            'authorized GitHub destination', 'setup blocker',
                            'acceptance criteria', 'Responsible Manager and executor',
                            'Priority never', 'next responsible participant', 'supplement'):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, text)

    def test_tracking_guidance_does_not_offer_local_execution_authority(self):
        for relative, obsolete in (
            ('docs/operations/task-continuity.md', 'existing GitHub/local tracker'),
            ('docs/operations/task-continuity.md', "Preserve the project's existing tracking mode"),
            ('docs/operations/adopting-dreamdocs.md', 'preserve its existing local/GitHub authority'),
            ('docs/operations/github-labels.md', 'preserves the chosen local/GitHub tracking'),
        ):
            with self.subTest(entry=relative, obsolete=obsolete):
                text = (ROOT / relative).read_text(encoding='utf-8')
                self.assertNotIn(obsolete, text)
                self.assertIn('pending-sync', text)


if __name__ == '__main__':
    unittest.main()
