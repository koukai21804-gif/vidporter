from __future__ import annotations

import threading
import time

import httpx
import pytest

from vidporter.web.server import STATIC_DIR, Handler, serve_ready
from vidporter.web.tasks import TaskManager

# -- TaskManager -------------------------------------------------------------


def test_task_success_and_progress():
    mgr = TaskManager()

    def work(task):
        task.set_progress(50, 100)
        task.log_line("处理中…")

    task = mgr.submit("download", "测试任务", work)
    deadline = time.time() + 5
    while time.time() < deadline and task.status == "running":
        time.sleep(0.02)
    assert task.status == "ok"
    assert task.progress_done == 50
    assert task.progress_total == 100
    assert any("处理中" in line for line in task.log)
    d = task.to_dict()
    assert d["status"] == "ok"


def test_task_failure_is_captured():
    mgr = TaskManager()

    def boom(task):
        raise RuntimeError("炸了")

    task = mgr.submit("download", "会失败", boom)
    deadline = time.time() + 5
    while time.time() < deadline and task.status == "running":
        time.sleep(0.02)
    assert task.status == "failed"
    assert any("炸了" in line for line in task.log)


def test_task_list_order_and_log_tail():
    mgr = TaskManager()

    def many_lines(task):
        for i in range(50):
            task.log_line(f"line-{i}")

    task = mgr.submit("download", "日志任务", many_lines)
    deadline = time.time() + 5
    while time.time() < deadline and task.status == "running":
        time.sleep(0.02)
    listing = mgr.list()
    assert listing[0]["id"] == task.id  # 最新的排前面
    assert len(listing[0]["log"]) <= 8  # 默认只回尾部日志


# -- HTTP API（本地起真实服务器，不联网） -------------------------------------


@pytest.fixture
def base_url():
    server, _port, thread = serve_ready(port=0, open_browser=False)
    url = f"http://127.0.0.1:{_port}"
    yield url
    server.shutdown()


def test_api_version_and_index(base_url):
    resp = httpx.get(f"{base_url}/api/version", timeout=5)
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert data["out_dir"]

    index = httpx.get(f"{base_url}/", timeout=5)
    assert index.status_code == 200
    assert "vidporter" in index.text
    assert STATIC_DIR.joinpath("index.html").is_file()


def test_api_convert_task_end_to_end(base_url, tmp_path):
    subs = tmp_path / "subs"
    subs.mkdir()
    (subs / "BV1demo.srt").write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n第一句\n\n2\n00:00:02,200 --> 00:00:04,000\n第二句\n",
        encoding="utf-8",
    )
    resp = httpx.post(
        f"{base_url}/api/convert",
        json={"subs_dir": str(subs)},
        timeout=5,
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # 轮询直到任务结束
    deadline = time.time() + 10
    status = "running"
    while time.time() < deadline and status == "running":
        listing = httpx.get(f"{base_url}/api/tasks", timeout=5).json()["tasks"]
        status = next(t["status"] for t in listing if t["id"] == task_id)
        time.sleep(0.05)
    assert status == "ok"

    out_md = subs.parent / "subs_md" / "BV1demo.md"
    assert out_md.exists()
    assert "第一句" in out_md.read_text(encoding="utf-8")


def test_api_validation_errors(base_url, tmp_path):
    # 缺少 url
    resp = httpx.post(f"{base_url}/api/info", json={}, timeout=5)
    assert resp.status_code == 400
    # 目录不存在
    resp = httpx.post(
        f"{base_url}/api/convert", json={"subs_dir": str(tmp_path / "nope")}, timeout=5
    )
    assert resp.status_code == 400
    # 未知路由
    resp = httpx.get(f"{base_url}/api/none", timeout=5)
    assert resp.status_code == 404


def test_handler_post_routes_declared():
    assert set(Handler.POST_ROUTES) == {
        "/api/info",
        "/api/download",
        "/api/login/bilibili",
        "/api/convert",
    }


def test_thread_safety_of_submit():
    mgr = TaskManager()
    done = threading.Event()

    def work(task):
        task.set_progress(1, 1)

    threads = [mgr.submit("download", f"t{i}", work) for i in range(20)]
    deadline = time.time() + 10
    while time.time() < deadline and any(t.status == "running" for t in threads):
        time.sleep(0.02)
    assert all(t.status == "ok" for t in threads)
    assert len(mgr.list(log_tail=0)) == 20
    done.set()
