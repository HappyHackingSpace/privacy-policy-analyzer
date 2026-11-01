from privacy_policy_analyzer import split_text_into_chunks


def test_split_text_into_chunks_empty_returns_empty():
    assert split_text_into_chunks("") == []


def test_split_text_into_chunks_respects_max_size():
    text = "Lorem ipsum " * 50
    chunks = split_text_into_chunks(text, chunk_size=120, chunk_overlap=20)
    assert len(chunks) >= 1
    assert all(len(c) <= 120 for c in chunks)
