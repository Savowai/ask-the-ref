from ask_the_ref.models import windows


class WordTokenizer:
    def encode(self, text, **kwargs):
        return text.split()

    def decode(self, tokens, **kwargs):
        return " ".join(tokens)


def test_long_sections_retain_tail_and_every_token():
    original = [f"word{i}" for i in range(2000)]
    pieces = list(windows(WordTokenizer(), " ".join(original), 254))
    assert all(len(p.split()) <= 254 for p in pieces)
    assert set(" ".join(pieces).split()) == set(original)
    assert pieces[-1].endswith("word1999")
