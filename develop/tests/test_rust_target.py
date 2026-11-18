from develop.builds import _collect_artifacts, _default_artifact_elf


def test_rust_mspm0_artifact_uses_package_name(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "Cargo.toml").write_text('[package]\nname = "team-firmware"\n')
    artifact = project / _default_artifact_elf("rust", "team-firmware")
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"\x7fELF")
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr("develop.builds.shutil.which", lambda binary: None)
    assert _collect_artifacts(project, output, "rust", "different-project-id", None)
    assert (output / "firmware.elf").read_bytes() == b"\x7fELF"
