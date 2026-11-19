from app.crypto import seed_from_secret, sign_hex, validation_signature, verify_callback_signature


OFFICIAL_SECRET = "DG5g3B4j9X2KOErG"
OFFICIAL_TOKEN = "Arq0D5A61EgUu4OxUvOp"
OFFICIAL_TS = "1725442341"
OFFICIAL_SIGNATURE = (
    "87befc99c42c651b3aac0278e71ada338433ae26fcb24307bdc5ad38c1adc2d01b"
    "cfcadc0842edac85e85205028a1132afe09280305f13aa6909ffc2d652c706"
)


def test_official_url_validation_signature():
    assert validation_signature(OFFICIAL_SECRET, OFFICIAL_TS, OFFICIAL_TOKEN) == OFFICIAL_SIGNATURE


def test_callback_signature_roundtrip():
    body = b'{"op":0,"d":{},"t":"GATEWAY_EVENT_NAME"}'
    timestamp = "1725442341"
    signature = sign_hex("naOC0ocQE3shWLAfffVLB1rhYPG7", timestamp.encode() + body)
    assert verify_callback_signature("naOC0ocQE3shWLAfffVLB1rhYPG7", timestamp, body, signature)
    assert not verify_callback_signature("naOC0ocQE3shWLAfffVLB1rhYPG7", timestamp, body + b"x", signature)


def test_seed_matches_go_byte_length():
    seed16 = seed_from_secret(OFFICIAL_SECRET)
    assert len(seed16) == 32
    assert seed16 == (OFFICIAL_SECRET * 2).encode("utf-8")[:32]
    secret32 = "a" * 32
    seed32 = seed_from_secret(secret32)
    assert seed32 == secret32.encode("utf-8")
