"""Optional Rust toolchain, isolated from the user's existing Rust installation."""

import json
import os
from pathlib import Path
import secrets
import shlex
import shutil


MARKER = ".dotfiles-rust-owner.json"
RELATIVE_ROOT = Path(".local/share/dotfiles/rust")
DEFAULT_COMPONENTS = ["clippy", "rustfmt", "rust-analyzer"]


def _root(home):
    return Path(os.path.abspath(os.fspath(home))) / RELATIVE_ROOT


def _check_path(home, root):
    """Reject symlinked parents before creating or removing our directory."""
    current = Path(os.path.abspath(os.fspath(home)))
    for part in RELATIVE_ROOT.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"Rust path is a symlink; left untouched: {current}")
        if current.exists() and not current.is_dir():
            raise RuntimeError(f"Rust path is not a directory: {current}")
    if current != root:
        raise RuntimeError("Unexpected Rust installation path")


def _validate_owner(root, record):
    if record.get("root") != str(root) or not record.get("owner"):
        raise RuntimeError(f"Rust ownership is unverified; left untouched: {root}")
    marker = root / MARKER
    if marker.is_symlink() or not marker.is_file():
        raise RuntimeError(f"Rust ownership marker is missing or unsafe: {marker}")
    try:
        actual = json.loads(marker.read_text())
    except (ValueError, OSError) as error:
        raise RuntimeError(f"Cannot verify Rust ownership: {marker}") from error
    expected = {"version": 1, "root": str(root), "owner": record["owner"]}
    if actual != expected:
        raise RuntimeError(f"Rust ownership marker does not match: {marker}")


def _external_rust(home):
    for name in ("CARGO_HOME", "RUSTUP_HOME"):
        if os.environ.get(name):
            return f"{name} is already configured"
    for relative in (".cargo", ".rustup"):
        path = Path(home) / relative
        if path.exists() or path.is_symlink():
            return f"existing {path}"
    for command in ("rustup", "rustc", "cargo"):
        if shutil.which(command):
            return f"existing {command} in PATH"
    return None


def _components(repo):
    manifest = Path(repo) / "packages.json" if repo is not None else None
    config = json.loads(manifest.read_text()) if manifest and manifest.is_file() else {}
    components = config.get("rust_components", DEFAULT_COMPONENTS)
    if not isinstance(components, list) or any(
            not isinstance(item, str) or not item or item.startswith("-")
            or any(character.isspace() for character in item) for item in components):
        raise ValueError("rust_components must be a list of component names")
    return list(dict.fromkeys(components))


def _write_env(root, provider_bin):
    cargo = root / "cargo"
    if cargo.is_symlink() or (cargo.exists() and not cargo.is_dir()):
        raise RuntimeError(f"Unsafe Cargo directory: {cargo}")
    cargo.mkdir(exist_ok=True)
    destination = cargo / "env"
    if destination.is_symlink():
        raise RuntimeError(f"Cargo environment is a symlink: {destination}")
    # Package-managed rustup provides the executable proxies. Its current
    # Homebrew formula no longer ships rustup-init or writes cargo/env.
    destination.write_text(
        "# Managed by personal dotfiles.\n"
        f"export CARGO_HOME={shlex.quote(str(cargo))}\n"
        f"export RUSTUP_HOME={shlex.quote(str(root / 'rustup'))}\n"
        "case \":$PATH:\" in\n"
        f"  *:{shlex.quote(str(provider_bin))}:*) ;;\n"
        f"  *) export PATH={shlex.quote(str(provider_bin))}:\"$PATH\" ;;\n"
        "esac\n"
        "case \":$PATH:\" in\n"
        "  *:\"$CARGO_HOME/bin\":*) ;;\n"
        "  *) export PATH=\"$CARGO_HOME/bin:$PATH\" ;;\n"
        "esac\n"
    )


def setup(repo, home, state, save, run, dry_run=False):
    """Install stable and useful components only into an owned, dedicated root.

    New installations use packages.json's rust_components (or defaults).
    Existing Rust is preserved, including the chosen default toolchain.
    Return a human-readable status; save() persists the shared state.
    """
    root = _root(home)
    record = state.get("rust", {})
    owned = bool(record.get("owner"))
    if not owned:
        existing = _external_rust(home)
        if existing:
            return f"Rust preserved ({existing})"
    _check_path(home, root)
    if root.exists():
        _validate_owner(root, record)
    elif owned and record.get("root") != str(root):
        raise RuntimeError("Rust state belongs to a different home")
    if dry_run:
        return f"Would install isolated Rust stable in {root}"

    brew = shutil.which("brew")
    if not brew:
        raise RuntimeError("Homebrew is required before setting up Rust")
    if not owned:
        record = {"root": str(root), "owner": secrets.token_hex(24), "status": "pending"}
        state["rust"] = record
        save()
    if not root.exists():
        root.mkdir(parents=True)
        with (root / MARKER).open("x") as marker:
            json.dump({"version": 1, "root": str(root), "owner": record["owner"]}, marker)

    try:
        if record.get("status") == "installed":
            # Also recognize state created before default_configured existed.
            record["default_configured"] = True
        installed = run([brew, "list", "--formula", "-1"], check=True)
        if "rustup" not in installed.stdout.splitlines():
            tools = state.setdefault("tools", {})
            pending = {"category": "formulae", "name": "rustup"}
            journal = tools.setdefault("pending", [])
            if pending not in journal:
                journal.append(pending)
            save()
            try:
                run([brew, "install", "rustup"], check=True, env={
                    **os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1",
                    "HOMEBREW_NO_INSTALL_CLEANUP": "1"})
            finally:
                # Capture packages installed even when Brew later reports an
                # error. If inventory fails, the manager reconciles pending.
                after = run([brew, "list", "--formula", "-1"], check=True)
                if "rustup" in after.stdout.splitlines():
                    formulae = tools.setdefault("formulae", [])
                    if "rustup" not in formulae:
                        formulae.append("rustup")
                journal.remove(pending)
                save()
        prefix = run([brew, "--prefix", "rustup"], check=True).stdout.strip()
        provider_bin = Path(prefix) / "bin"
        if not prefix or not Path(prefix).is_absolute():
            raise RuntimeError("Homebrew returned an invalid rustup prefix")
        environment = os.environ.copy()
        environment.update(CARGO_HOME=str(root / "cargo"), RUSTUP_HOME=str(root / "rustup"))
        environment.pop("RUSTUP_TOOLCHAIN", None)
        # Never assign HOME: these two explicit homes keep rustup isolated.
        for name in ("cargo", "rustup"):
            child = root / name
            if child.is_symlink() or (child.exists() and not child.is_dir()):
                raise RuntimeError(f"Unsafe Rust directory: {child}")
        rustup = str(provider_bin / "rustup")
        toolchains = run([rustup, "toolchain", "list"], check=True, env=environment)
        stable_exists = any(
            line.split()[0] == "stable" or line.split()[0].startswith("stable-")
            for line in toolchains.stdout.splitlines() if line.strip())
        needs_install = record.get("status") != "installed" or not stable_exists
        if needs_install:
            components = record.get("components")
            if components is None:
                components = _components(repo)
                record["components"] = components
                save()
            command = [rustup, "toolchain", "install", "stable", "--profile", "minimal"]
            for component in components:
                command.extend(["--component", component])
            run(command, check=True, env=environment)
        if not record.get("default_configured"):
            run([rustup, "default", "stable"], check=True, env=environment)
            record["default_configured"] = True
            save()
        _write_env(root, provider_bin)
        record.update(status="installed", provider_bin=str(provider_bin))
        save()
    except Exception:
        record["status"] = "incomplete"
        save()
        raise
    return f"Rust stable {'installed' if needs_install else 'preserved'} in {root}"


def purge(home, state, save, run, dry_run=False):
    """Remove only the root authenticated by both state and ownership marker.

    Formula removal is the lifecycle manager's job. rmtree unlinks nested
    symlinks without following them; parent and root symlinks are rejected.
    """
    record = state.get("rust", {})
    if not record.get("owner"):
        return "No managed Rust installation to remove"
    root = _root(home)
    _check_path(home, root)
    if record.get("root") != str(root):
        raise RuntimeError("Rust state belongs to a different home")
    if root.exists():
        _validate_owner(root, record)
        if dry_run:
            return f"Would remove managed Rust in {root}"
        shutil.rmtree(root)
    elif dry_run:
        return "Managed Rust directory is already absent"
    state.pop("rust", None)
    save()
    return f"Managed Rust removed from {root}"
