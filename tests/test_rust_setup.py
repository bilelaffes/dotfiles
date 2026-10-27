import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location(
    "rust_setup", Path(__file__).resolve().parents[1] / "scripts/rust_setup.py"
)
rust = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rust)


class RustSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.state = {}
        self.save = Mock()
        self.installed = False
        self.failure = False
        self.toolchains = ""
        self.calls = []
        self.env_patch = patch.dict(os.environ, {"CARGO_HOME": "", "RUSTUP_HOME": "", "RUSTUP_TOOLCHAIN": ""})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.which_patch = patch.object(rust.shutil, "which", side_effect=lambda name: "/brew/bin/brew" if name == "brew" else None)
        self.which_patch.start()
        self.addCleanup(self.which_patch.stop)

    def runner(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if cmd[1:] == ["list", "--formula", "-1"]:
            return subprocess.CompletedProcess(cmd, 0, "rustup\n" if self.installed else "", "")
        if cmd[1:] == ["install", "rustup"]:
            self.installed = True
        if cmd[1:] == ["--prefix", "rustup"]:
            return subprocess.CompletedProcess(cmd, 0, "/brew/opt/rustup\n", "")
        if cmd[1:] == ["toolchain", "list"]:
            return subprocess.CompletedProcess(cmd, 0, self.toolchains, "")
        if cmd[1:3] == ["toolchain", "install"]:
            if self.failure:
                raise subprocess.CalledProcessError(1, cmd)
            self.toolchains = "stable-aarch64-apple-darwin (default)\n"
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def setup_rust(self, **kwargs):
        return rust.setup(None, self.home, self.state, self.save, self.runner, **kwargs)

    def test_success_is_isolated_and_records_new_formula(self):
        original_home = os.environ.get("HOME")
        self.setup_rust()
        self.assertEqual(self.state["tools"]["formulae"], ["rustup"])
        self.assertEqual(self.state["rust"]["status"], "installed")
        root = rust._root(self.home)
        for cmd, kwargs in self.calls:
            if cmd[0].endswith("/rustup"):
                self.assertEqual(kwargs["env"].get("HOME"), original_home)
                self.assertEqual(kwargs["env"]["CARGO_HOME"], str(root / "cargo"))
                self.assertEqual(kwargs["env"]["RUSTUP_HOME"], str(root / "rustup"))
        command = next(cmd for cmd, _ in self.calls if cmd[1:3] == ["toolchain", "install"])
        for component in ("clippy", "rustfmt", "rust-analyzer"):
            self.assertIn(component, command)
        env = (root / "cargo/env").read_text()
        self.assertIn("export RUSTUP_HOME=", env)
        self.assertIn("/brew/opt/rustup/bin", env)
        subprocess.run(["/bin/bash", "-n", str(root / "cargo/env")], check=True)
        self.assertFalse((self.home / ".cargo").exists())

    def test_existing_cargo_is_preserved(self):
        (self.home / ".cargo").mkdir()
        self.assertIn("preserved", self.setup_rust())
        self.assertEqual(self.state, {})
        self.assertEqual(self.calls, [])

    def test_existing_rustup_in_path_is_preserved(self):
        with patch.object(rust.shutil, "which", return_value="/other/bin/rustup"):
            self.assertIn("preserved", self.setup_rust())
        self.assertEqual(self.calls, [])

    def test_custom_homes_are_preserved_even_if_not_created(self):
        for name in ("CARGO_HOME", "RUSTUP_HOME"):
            with self.subTest(name=name), patch.dict(os.environ, {name: "/foreign/rust"}):
                self.assertIn("preserved", self.setup_rust())
        self.assertEqual(self.state, {})

    def test_existing_formula_is_not_claimed(self):
        self.installed = True
        self.setup_rust()
        self.assertNotIn("tools", self.state)

    def test_dry_run_has_no_writes_or_commands(self):
        self.setup_rust(dry_run=True)
        self.assertEqual(self.state, {})
        self.assertEqual(self.calls, [])
        self.save.assert_not_called()
        self.assertFalse(rust._root(self.home).exists())

    def test_failure_can_resume_without_reclaiming_formula(self):
        self.failure = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.setup_rust()
        self.assertEqual(self.state["rust"]["status"], "incomplete")
        owner = self.state["rust"]["owner"]
        self.failure = False
        self.setup_rust()
        self.assertEqual(self.state["rust"]["owner"], owner)
        self.assertEqual(self.state["tools"]["formulae"], ["rustup"])
        self.assertEqual(sum(cmd[1:] == ["install", "rustup"] for cmd, _ in self.calls), 1)

    def test_rerun_preserves_installed_stable_and_user_default(self):
        self.setup_rust()
        self.calls.clear()
        self.toolchains = "stable-aarch64-apple-darwin\nnightly-aarch64-apple-darwin (default)\n"
        self.assertIn("preserved", self.setup_rust())
        self.assertTrue(any(cmd[1:] == ["toolchain", "list"] for cmd, _ in self.calls))
        self.assertFalse(any(cmd[1:3] == ["toolchain", "install"] or cmd[1] == "default" for cmd, _ in self.calls))

    def test_missing_owned_stable_is_repaired_without_resetting_default(self):
        self.setup_rust()
        self.calls.clear()
        self.toolchains = "nightly-x86_64-unknown-linux-gnu (default)\n"
        self.setup_rust()
        self.assertTrue(any(cmd[1:3] == ["toolchain", "install"] for cmd, _ in self.calls))
        self.assertFalse(any(cmd[1] == "default" for cmd, _ in self.calls))

    def test_manifest_components_used_for_new_installation(self):
        repo = Path(self.temp.name) / "repo"
        repo.mkdir()
        (repo / "packages.json").write_text(json.dumps({"rust_components": ["rust-src", "rustfmt"]}))
        rust.setup(repo, self.home, self.state, self.save, self.runner)
        command = next(cmd for cmd, _ in self.calls if cmd[1:3] == ["toolchain", "install"])
        self.assertEqual(command[7:], ["rust-src", "--component", "rustfmt"])
        self.assertNotIn("clippy", command)
        self.assertEqual(self.state["rust"]["components"], ["rust-src", "rustfmt"])
        (repo / "packages.json").write_text(json.dumps({"rust_components": ["clippy"]}))
        self.calls.clear()
        rust.setup(repo, self.home, self.state, self.save, self.runner)
        self.assertFalse(any(cmd[1:3] == ["toolchain", "install"] for cmd, _ in self.calls))

    def test_external_rust_does_not_read_or_apply_manifest_components(self):
        (self.home / ".cargo").mkdir()
        repo = Path(self.temp.name) / "repo"
        repo.mkdir()
        (repo / "packages.json").write_text("not json")
        self.assertIn("preserved", rust.setup(repo, self.home, self.state, self.save, self.runner))
        self.assertEqual(self.calls, [])

    def test_unmarked_existing_root_is_not_adopted(self):
        root = rust._root(self.home)
        root.mkdir(parents=True)
        with self.assertRaises(RuntimeError):
            self.setup_rust()
        self.assertEqual(self.state, {})
        self.assertTrue(root.exists())

    def test_symlink_parent_refused(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.home / ".local").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            self.setup_rust()
        self.assertEqual(list(outside.iterdir()), [])

    def test_purge_preserves_nested_symlink_target(self):
        self.setup_rust()
        outside = Path(self.temp.name) / "foreign-toolchain"
        outside.mkdir()
        (outside / "keep").write_text("preserve")
        (rust._root(self.home) / "linked").symlink_to(outside, target_is_directory=True)
        rust.purge(self.home, self.state, self.save, self.runner)
        self.assertEqual((outside / "keep").read_text(), "preserve")
        self.assertFalse(rust._root(self.home).exists())
        self.assertNotIn("rust", self.state)
        self.assertEqual(self.state["tools"]["formulae"], ["rustup"])

    def test_purge_refuses_missing_or_mismatched_marker(self):
        self.setup_rust()
        marker = rust._root(self.home) / rust.MARKER
        for content in (None, "{}", "broken"):
            with self.subTest(content=content):
                if content is None:
                    marker.unlink()
                else:
                    marker.write_text(content)
                with self.assertRaises(RuntimeError):
                    rust.purge(self.home, self.state, self.save, self.runner)
                self.assertTrue(rust._root(self.home).exists())

    def test_purge_refuses_symlink_root_and_marker(self):
        self.setup_rust()
        root = rust._root(self.home)
        moved = root.with_name("foreign")
        root.rename(moved)
        root.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            rust.purge(self.home, self.state, self.save, self.runner)
        root.unlink()
        moved.rename(root)
        marker = root / rust.MARKER
        original = marker.with_name("original-marker")
        marker.rename(original)
        marker.symlink_to(original)
        with self.assertRaises(RuntimeError):
            rust.purge(self.home, self.state, self.save, self.runner)

    def test_purge_dry_run_keeps_state_and_files(self):
        self.setup_rust()
        before = json.dumps(self.state)
        self.save.reset_mock()
        rust.purge(self.home, self.state, self.save, self.runner, dry_run=True)
        self.assertEqual(json.dumps(self.state), before)
        self.assertTrue(rust._root(self.home).exists())
        self.save.assert_not_called()

    def test_failed_brew_install_records_only_observed_package(self):
        def failing_brew(cmd, **kwargs):
            result = self.runner(cmd, **kwargs)
            if cmd[1:] == ["install", "rustup"]:
                raise subprocess.CalledProcessError(1, cmd)
            return result
        with self.assertRaises(subprocess.CalledProcessError):
            rust.setup(None, self.home, self.state, self.save, failing_brew)
        self.assertEqual(self.state["tools"]["formulae"], ["rustup"])
        self.assertEqual(self.state["tools"]["pending"], [])
        self.assertEqual(self.state["rust"]["status"], "incomplete")

    def test_inventory_failure_retains_pending_journal(self):
        def unavailable_inventory(cmd, **kwargs):
            if self.installed and cmd[1:] == ["list", "--formula", "-1"]:
                raise subprocess.CalledProcessError(1, cmd)
            return self.runner(cmd, **kwargs)
        with self.assertRaises(subprocess.CalledProcessError):
            rust.setup(None, self.home, self.state, self.save, unavailable_inventory)
        self.assertEqual(self.state["tools"]["pending"], [{"category": "formulae", "name": "rustup"}])
        self.assertNotIn("formulae", self.state["tools"])


if __name__ == "__main__":
    unittest.main()
