import sys
import types

import pytest

from agents.da_code_index import WORK_ONLY_MESSAGE, FakeEmbedder, WorkEmbedder


def test_fake_same_text_same_vector():
    fake = FakeEmbedder()
    assert fake.embed("hello") == fake.embed("hello")
    assert fake.embed("hello") != fake.embed("other")
    assert len(fake.embed("x")) == 8


def test_work_embedder_at_home_says_work_only(monkeypatch):
    monkeypatch.setitem(sys.modules, "agents.a_vector", None)  # import fails
    with pytest.raises(RuntimeError, match=WORK_ONLY_MESSAGE):
        WorkEmbedder().embed("x")


def test_work_embedder_with_stub_module_and_never_logs_text(monkeypatch, caplog):
    stub = types.ModuleType("agents.a_vector")
    stub.create_embeddings = lambda text: [[1.0, 2.0]]
    monkeypatch.setitem(sys.modules, "agents.a_vector", stub)
    with caplog.at_level("DEBUG"):
        assert WorkEmbedder().embed("SECRET-TEXT") == [1.0, 2.0]
    assert "SECRET-TEXT" not in caplog.text


def test_work_embedder_none_when_service_fails(monkeypatch):
    stub = types.ModuleType("agents.a_vector")
    stub.create_embeddings = lambda text: None
    monkeypatch.setitem(sys.modules, "agents.a_vector", stub)
    assert WorkEmbedder().embed("x") is None
