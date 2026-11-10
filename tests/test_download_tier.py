# coding=utf-8
"""AC-06 / PRD §5：L1~L4 四档行为、本地文件缺失降级、不伪造文件、无静默失败。"""

from __future__ import annotations

from scripts.bidding_scraper.download_resolver import (
    DownloadResolver,
    is_safe_url,
    resolve,
)
from scripts.bidding_scraper.snapshot import SnapshotStore


class TestFourTiers:
    def test_l1_direct_http_attachment(self, make_download_config, make_item):
        item = make_item(title="中国铁塔招标文件")
        item.attachment_url = "https://ebid.chinatowercom.cn/files/abc.pdf"

        tier = DownloadResolver(download_config=make_download_config()).resolve(item)

        assert tier.level == "L1"
        assert tier.enabled is True
        assert tier.url == item.attachment_url
        assert tier.filename.endswith(".pdf")

    def test_l4_disabled_empty_url_and_no_fake_file(self, make_download_config, make_item):
        item = make_item(title="中国铁塔无附件公告")

        tier = DownloadResolver(download_config=make_download_config()).resolve(item)

        assert tier.level == "L4"
        assert tier.enabled is False
        assert tier.url == ""
        assert tier.note and "不提供下载" in tier.note  # 明确提示，不是静默失败

    def test_l2_missing_local_file_downgrades_to_l4(self, make_download_config, make_item):
        item = make_item(title="中国铁塔副本公告")
        item.attachment_url = "attachments/definitely-missing-file-qa.pdf"

        tier = DownloadResolver(download_config=make_download_config()).resolve(item)

        assert tier.level == "L4" and tier.enabled is False and tier.url == ""

    def test_l3_missing_snapshot_downgrades_to_l4(self, make_download_config, make_item):
        item = make_item(title="中国铁塔快照公告")
        item.snapshot_url = "snapshots/definitely-missing-snapshot-qa.html"

        tier = DownloadResolver(download_config=make_download_config()).resolve(item)

        assert tier.level == "L4" and tier.enabled is False and tier.url == ""

    def test_l2_real_local_file(self, tmp_path, make_download_config, make_item):
        att_dir = tmp_path / "attachments"
        att_dir.mkdir()
        real = att_dir / "源文件副本.pdf"
        real.write_bytes(b"%PDF-1.4 QA")
        item = make_item(title="中国铁塔副本公告")
        item.attachment_url = str(real)

        tier = DownloadResolver(
            download_config=make_download_config(attachments_dir=att_dir)
        ).resolve(item)

        assert tier.level == "L2" and tier.enabled is True
        assert tier.url == "attachments/源文件副本.pdf"

    def test_l3_real_local_snapshot(self, tmp_path, make_download_config, make_item):
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        real = snap_dir / "detail.html"
        real.write_text("<html>QA</html>", encoding="utf-8")
        item = make_item(title="中国铁塔快照公告")
        item.snapshot_url = str(real)

        tier = DownloadResolver(
            download_config=make_download_config(snapshots_dir=snap_dir)
        ).resolve(item)

        assert tier.level == "L3" and tier.enabled is True
        assert tier.url == "snapshots/detail.html"
        assert tier.filename.endswith(".html")

    def test_javascript_scheme_never_becomes_l1(self, make_download_config, make_item):
        item = make_item(title="中国铁塔恶意链接")
        item.attachment_url = "javascript:alert(1)"

        tier = DownloadResolver(download_config=make_download_config()).resolve(item)

        assert is_safe_url(item.attachment_url) is False
        assert tier.level == "L4" and tier.enabled is False and tier.url == ""

    def test_tier_to_dict_contract(self, make_download_config, make_item):
        tier = DownloadResolver(download_config=make_download_config()).resolve(make_item())
        assert set(tier.to_dict()) == {"level", "url", "filename", "note", "enabled"}
        assert tier.level in {"L1", "L2", "L3", "L4"}

    def test_module_level_resolve_uses_default_config(self, make_item):
        tier = resolve(make_item())
        assert tier.level == "L4" and tier.enabled is False


class TestSnapshotStoreOffline:
    def test_prefetch_off_never_issues_network_request(self, monkeypatch, make_download_config):
        def boom(*args, **kwargs):
            raise AssertionError("离线优先：不应发起任何网络请求")

        monkeypatch.setattr("scripts.bidding_scraper.snapshot.requests.get", boom)
        store = SnapshotStore(download_config=make_download_config(prefetch=False))

        assert store.prefetch is False
        assert store.save("https://example.com/detail", "dedup-key") == ""
        assert store.save_attachment("https://example.com/a.pdf", "dedup-key") == ""
