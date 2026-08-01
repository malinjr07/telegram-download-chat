"""Tests for splitting TXT chat records by file size with citation thread preservation."""

from pathlib import Path
import pytest
from telegram_download_chat.cli.arguments import parse_args
from telegram_download_chat.cli.commands import split_messages_by_size
from telegram_download_chat.core.messages import MessagesMixin


class MockDownloader(MessagesMixin):
    def __init__(self):
        self.logger = None
        self._fetched_usernames_count = 0
        self._fetched_chatnames_count = 0

    def _get_sender_id(self, msg):
        return msg.get("from_id")

    async def _get_user_display_name(self, sender_id):
        return f"User{sender_id}"

    def _get_recipient_id(self, msg):
        return None

    async def _get_peer_display_name(self, recipient_id):
        return ""

    def _save_config(self):
        pass


@pytest.mark.asyncio
async def test_group_messages_by_thread():
    downloader = MockDownloader()
    messages = [
        {"id": 1, "date": "2026-01-01T10:00:00Z", "text": "Root message 1", "from_id": 100},
        {"id": 2, "date": "2026-01-01T10:05:00Z", "text": "Reply to root 1", "from_id": 101, "reply_to": {"reply_to_msg_id": 1}},
        {"id": 3, "date": "2026-01-01T10:10:00Z", "text": "Root message 2", "from_id": 102},
        {"id": 4, "date": "2026-01-01T10:15:00Z", "text": "Reply to reply 2", "from_id": 103, "reply_to": {"reply_to_msg_id": 2}},
    ]

    groups = downloader.group_messages_by_thread(messages, sort_order="asc")
    # Message 1, 2, 4 belong to thread group 1. Message 3 belongs to thread group 2.
    assert len(groups) == 2
    thread1_ids = [m["id"] for m in groups[0]]
    thread2_ids = [m["id"] for m in groups[1]]

    assert thread1_ids == [1, 2, 4]
    assert thread2_ids == [3]


@pytest.mark.asyncio
async def test_save_messages_as_txt_size_splitting(tmp_path):
    downloader = MockDownloader()
    # Create several messages with long text so file size threshold is triggered
    long_text_1 = "A" * 150
    long_text_2 = "B" * 150
    long_text_3 = "C" * 150

    messages = [
        {"id": 1, "date": "2026-01-01T10:00:00Z", "text": long_text_1, "from_id": 100},
        {"id": 2, "date": "2026-01-01T10:05:00Z", "text": "Reply to 1: " + long_text_2, "from_id": 101, "reply_to": {"reply_to_msg_id": 1}},
        {"id": 3, "date": "2026-01-01T10:10:00Z", "text": long_text_3, "from_id": 102},
    ]

    txt_file = tmp_path / "chat_export.txt"

    # Set max_file_size_bytes small enough (e.g. 250 bytes) so thread 1 fits in part 1, and thread 2 goes to part 2
    saved = await downloader.save_messages_as_txt(
        messages,
        txt_file,
        sort_order="asc",
        max_file_size_bytes=250,
    )

    assert saved == 3
    part1_file = tmp_path / "chat_export_part1.txt"
    part2_file = tmp_path / "chat_export_part2.txt"

    assert part1_file.exists()
    assert part2_file.exists()

    part1_content = part1_file.read_text(encoding="utf-8")
    part2_content = part2_file.read_text(encoding="utf-8")

    # Thread 1 (root 1 + reply 2) MUST be in part1 together without being split
    assert long_text_1 in part1_content
    assert "Reply to 1" in part1_content
    # Thread 2 (root 3) MUST be in part2
    assert long_text_3 in part2_content


@pytest.mark.asyncio
async def test_split_messages_by_size_helper():
    downloader = MockDownloader()
    messages = [
        {"id": 1, "date": "2026-01-01T10:00:00Z", "text": "X" * 150, "from_id": 100},
        {"id": 2, "date": "2026-01-01T10:05:00Z", "text": "Y" * 150, "from_id": 101},
    ]

    # Threshold of 200 bytes will split 2 separate root messages into part1 and part2
    result = await split_messages_by_size(downloader, messages, max_bytes=200)

    assert "part1" in result
    assert "part2" in result
    assert len(result["part1"]) == 1
    assert len(result["part2"]) == 1
    assert result["part1"][0]["id"] == 1
    assert result["part2"][0]["id"] == 2


def test_cli_arguments_split_size():
    opts = parse_args(["chatname", "--split", "size", "--max-txt-size", "2.6"])
    assert opts.split == "size"
    assert opts.max_txt_size == 2.6
