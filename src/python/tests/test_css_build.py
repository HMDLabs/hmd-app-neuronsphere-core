"""css/build.sh builds deployments/css/app.css with a Tailwind CLI
taken from $TAILWINDCSS, the pre_build_artifacts folder (one binary per
platform) or the PATH. The CLI here is a stub that records its arguments."""

import os
import pathlib
import shutil
import stat
import subprocess

import pytest

CSS_DIR = pathlib.Path(__file__).resolve().parent.parent / "css"
OUT_REL = "deployments/static/deployments/css/app.css"

STUB = """#!/bin/sh
echo "$@" > "$(dirname "$0")/args.txt"
out=""
while [ $# -gt 0 ]; do [ "$1" = "--output" ] && out="$2"; shift; done
echo "/* built by $(basename "$(dirname "$0")") */" > "$out"
"""


@pytest.fixture
def tree(tmp_path):
    css = tmp_path / "css"
    css.mkdir()
    shutil.copy(CSS_DIR / "build.sh", css / "build.sh")
    (css / "app.src.css").write_text("/* input */")
    (tmp_path / OUT_REL).parent.mkdir(parents=True)
    return tmp_path


def stub(path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STUB)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def run(tree, **env):
    clean = {
        k: v
        for k, v in os.environ.items()
        if k not in ("TAILWINDCSS", "TAILWINDCSS_PLATFORM")
    }
    clean["PATH"] = "/usr/bin:/bin"  # no tailwindcss on the PATH
    clean.update(env)
    return subprocess.run(
        ["sh", str(tree / "css" / "build.sh")],
        capture_output=True,
        text=True,
        env=clean,
    )


def test_build_fails_clearly_when_no_cli_is_found(tree):
    result = run(tree)
    assert result.returncode != 0
    assert "Tailwind CLI" in result.stderr and "TAILWINDCSS" in result.stderr
    assert not (tree / OUT_REL).exists()


def test_tailwindcss_variable_wins(tree):
    cli = stub(tree / "elsewhere" / "tailwindcss")
    stub(tree / "css" / "bin" / "linux-x64" / "tailwindcss")
    result = run(tree, TAILWINDCSS=str(cli), TAILWINDCSS_PLATFORM="linux-x64")
    assert result.returncode == 0, result.stderr
    assert "elsewhere" in (tree / OUT_REL).read_text()


@pytest.mark.parametrize("platform", ["linux-x64", "linux-arm64", "macos-arm64"])
def test_the_artifact_binary_for_the_platform_is_used(tree, platform):
    for p in ("linux-x64", "linux-arm64", "macos-arm64"):
        stub(tree / "css" / "bin" / p / "tailwindcss")
        # the artifact unzips without the executable bit
        (tree / "css" / "bin" / p / "tailwindcss").chmod(0o644)
    result = run(tree, TAILWINDCSS_PLATFORM=platform)
    assert result.returncode == 0, result.stderr
    assert f"built by {platform}" in (tree / OUT_REL).read_text()


def test_platform_is_derived_from_uname(tree):
    system, machine = os.uname().sysname, os.uname().machine
    mapping = {
        ("Darwin", "arm64"): "macos-arm64",
        ("Linux", "x86_64"): "linux-x64",
        ("Linux", "aarch64"): "linux-arm64",
        ("Linux", "arm64"): "linux-arm64",
    }
    platform = mapping.get((system, machine))
    if platform is None:
        pytest.skip(f"no Tailwind binary for {system} {machine}")
    stub(tree / "css" / "bin" / platform / "tailwindcss")
    result = run(tree)
    assert result.returncode == 0, result.stderr
    assert f"built by {platform}" in (tree / OUT_REL).read_text()


def test_unsupported_platform_is_named(tree):
    result = run(tree, TAILWINDCSS_PLATFORM="plan9-mips")
    assert result.returncode != 0 and "plan9-mips" in result.stderr


def test_the_cli_gets_the_input_the_output_and_minify(tree):
    cli = stub(tree / "bin" / "tailwindcss")
    run(tree, TAILWINDCSS=str(cli))
    args = (tree / "bin" / "args.txt").read_text()
    assert "--input app.src.css" in args and "--minify" in args
    assert OUT_REL in args


def test_a_failed_build_leaves_no_stale_css(tree):
    (tree / OUT_REL).write_text("/* stale */")
    failing = tree / "bin" / "tailwindcss"
    failing.parent.mkdir()
    failing.write_text("#!/bin/sh\nexit 3\n")
    failing.chmod(0o755)
    result = run(tree, TAILWINDCSS=str(failing))
    assert result.returncode != 0
    assert not (tree / OUT_REL).exists()
