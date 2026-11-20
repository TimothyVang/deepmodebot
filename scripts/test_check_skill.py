"""Unit tests for the shipped per-skill validator (scripts/check_skill.py)."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK_SKILL_PATH = next(ROOT.glob("plugins/*/skills/*/scripts/check_skill.py"))
SPEC = importlib.util.spec_from_file_location("check_skill_mod", CHECK_SKILL_PATH)
check_skill = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_skill
SPEC.loader.exec_module(check_skill)


class CheckSkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="check-skill-test-")
        self.addCleanup(self.tmp.cleanup)
        self.skills_root = Path(self.tmp.name) / "skills"
        self.skills_root.mkdir()

    def write_skill(self, name, body, frontmatter=None, extra_files=None):
        skill_dir = self.skills_root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        if frontmatter is not None:
            text = f"---\n{frontmatter}\n---\n{body}"
        else:
            text = body
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
        for rel, content in (extra_files or {}).items():
            dest = skill_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        return skill_dir

    def run_cli(self, *skill_dirs):
        return subprocess.run(
            [sys.executable, "-B", str(CHECK_SKILL_PATH), *(str(d) for d in skill_dirs)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_valid_skill_with_local_and_sibling_links_passes(self):
        sibling = self.write_skill(
            "helper-skill",
            "Helper body.\n",
            frontmatter='name: helper-skill\ndescription: "Helper skill."',
            extra_files={"references/other.md": "# Other\n"},
        )
        main = self.write_skill(
            "demo-skill",
            "Read `references/guide.md` and `skill://helper-skill/references/other.md`.\n",
            frontmatter='name: demo-skill\ndescription: "Demo skill."',
            extra_files={"references/guide.md": "# Guide\n"},
        )
        skills = {"helper-skill": sibling, "demo-skill": main}
        self.assertEqual(check_skill.check(main, skills, listed=False), [])

        cli = self.run_cli(main)
        self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)
        self.assertEqual(cli.stdout.strip().splitlines()[-1], "ok")

    def test_missing_skill_md_or_incomplete_frontmatter_fails(self):
        empty_dir = self.skills_root / "empty-skill"
        empty_dir.mkdir()
        missing_res = check_skill.check(empty_dir, {}, listed=False)
        self.assertTrue(any("no SKILL.md" in item for item in missing_res), missing_res)
        self.assertEqual(self.run_cli(empty_dir).returncode, 1)

        no_fm = self.write_skill("no-fm", "# Missing frontmatter\n", frontmatter=None)
        no_fm_res = check_skill.check(no_fm, {"no-fm": no_fm}, listed=False)
        self.assertTrue(any("frontmatter needs name and description" in item for item in no_fm_res), no_fm_res)

        no_desc = self.write_skill("no-desc", "Body\n", frontmatter="name: no-desc")
        no_desc_res = check_skill.check(no_desc, {"no-desc": no_desc}, listed=False)
        self.assertTrue(any("frontmatter needs name and description" in item for item in no_desc_res), no_desc_res)
        self.assertEqual(self.run_cli(no_desc).returncode, 1)

    def test_broken_local_reference_link_fails(self):
        broken = self.write_skill(
            "broken-local",
            "See `references/missing.md` for details.\n",
            frontmatter='name: broken-local\ndescription: "Broken local ref."',
        )
        problems = check_skill.check(broken, {"broken-local": broken}, listed=False)
        self.assertEqual(len(problems), 1)
        self.assertIn("references/missing.md does not exist", problems[0])
        cli = self.run_cli(broken)
        self.assertEqual(cli.returncode, 1)
        self.assertIn("references/missing.md does not exist", cli.stdout)

    def test_broken_sibling_skill_file_link_fails(self):
        sibling = self.write_skill(
            "sibling-skill",
            "Sibling.\n",
            frontmatter='name: sibling-skill\ndescription: "Sibling."',
        )
        caller = self.write_skill(
            "caller-skill",
            "See `skill://sibling-skill/references/nope.md`.\n",
            frontmatter='name: caller-skill\ndescription: "Caller."',
        )
        skills = {"sibling-skill": sibling, "caller-skill": caller}
        problems = check_skill.check(caller, skills, listed=False)
        self.assertEqual(len(problems), 1)
        self.assertIn("skill://sibling-skill/references/nope.md does not exist", problems[0])
        cli = self.run_cli(caller)
        self.assertEqual(cli.returncode, 1)
        self.assertIn("skill://sibling-skill/references/nope.md does not exist", cli.stdout)


if __name__ == "__main__":
    unittest.main()
