from agents.da_code_index import FakeEmbedder


def test_fake_same_text_same_vector():
    fake = FakeEmbedder()
    assert fake.embed("hello") == fake.embed("hello")
    assert fake.embed("hello") != fake.embed("other")
    assert len(fake.embed("x")) == 8

# WorkEmbedder now runs CodeVision's embedder in a helper process: see test_da_embed_worker.py.
