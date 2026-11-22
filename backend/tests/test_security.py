from logbook.security import COOKIE, SESSION_TTL, dummy_hash, hasher, new_session, session_hash, verify_password


def test_password_round_trip():
    digest = hasher.hash("correct horse battery staple")
    assert verify_password(digest, "correct horse battery staple") is True
    assert verify_password(digest, "wrong password") is False


def test_invalid_hash_is_rejected_without_raising():
    assert verify_password("not-a-hash", "whatever") is False
    assert verify_password(dummy_hash, "whatever it was") is False


def test_rehash_is_only_needed_for_old_parameters():
    digest = hasher.hash("correct horse battery staple")
    assert hasher.check_needs_rehash(digest) is False


def test_session_tokens_are_random_and_hashed():
    tokens = {new_session() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(token) >= 40 for token in tokens)
    digest = session_hash(tokens.pop())
    assert isinstance(digest, bytes) and len(digest) == 32


def test_session_shape():
    assert SESSION_TTL.days == 7
    assert COOKIE in {"logbook", "__Host-logbook"}
