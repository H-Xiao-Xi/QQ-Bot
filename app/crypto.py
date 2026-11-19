"""Ed25519 helpers matching QQ Bot webhook docs."""

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

ED25519_SEED_SIZE = 32
ED25519_SIGNATURE_SIZE = 64


def seed_from_secret(secret: str) -> bytes:
    # Go uses string byte length, then ed25519.GenerateKey(strings.NewReader(seed[:32])).
    seed = secret.encode("utf-8")
    while len(seed) < ED25519_SEED_SIZE:
        seed = seed * 2
    return seed[:ED25519_SEED_SIZE]


def signing_key_from_secret(secret: str) -> SigningKey:
    return SigningKey(seed_from_secret(secret))


def verify_key_from_secret(secret: str) -> VerifyKey:
    return signing_key_from_secret(secret).verify_key


def sign_hex(secret: str, message: bytes) -> str:
    signed = signing_key_from_secret(secret).sign(message)
    return signed.signature.hex()


def validation_signature(secret: str, event_ts: str, plain_token: str) -> str:
    return sign_hex(secret, f"{event_ts}{plain_token}".encode("utf-8"))


def verify_callback_signature(
    secret: str,
    timestamp: str,
    body: bytes,
    signature_hex: str,
) -> bool:
    if not timestamp or not signature_hex:
        return False
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    if len(signature) != ED25519_SIGNATURE_SIZE:
        return False
    if signature[63] & 224:
        return False
    try:
        verify_key_from_secret(secret).verify(timestamp.encode("utf-8") + body, signature)
    except BadSignatureError:
        return False
    return True
