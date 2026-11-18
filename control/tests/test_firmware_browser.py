from control.routers.target import list_firmware


def test_firmware_folder_lists_images_and_rust_elf(tmp_path):
    (tmp_path / "team").mkdir()
    (tmp_path / "team" / "attack.prot").write_bytes(b"payload")
    (tmp_path / "team" / "standalone").write_bytes(b"\x7fELFtest")
    (tmp_path / "team" / "notes.txt").write_text("not firmware")
    (tmp_path / "team" / "link.bin").symlink_to(tmp_path / "team" / "attack.prot")
    result = list_firmware(str(tmp_path))
    assert [(i["name"], i["mode"]) for i in result["images"]] == [
        ("team/attack.prot", "ectf"), ("team/standalone", "swd")]
