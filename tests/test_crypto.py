from app.crypto import sign_hex, validation_signature, verify_callback_signature


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
