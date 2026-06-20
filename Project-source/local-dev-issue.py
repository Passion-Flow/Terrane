"""本地联调：生成测试密钥对 + 签发绑定本机指纹的离线 License，输出 env 与 blob。"""
import base64, datetime, json, os, sys
sys.path.insert(0, "terrane-admin-server/app/vendor")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

def b64u(b): return base64.urlsafe_b64encode(b).decode().rstrip("=")

priv = Ed25519PrivateKey.generate()
pub_pem = priv.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
entry = {"key_id": "dev", "alg": "ed25519", "public_key": pub_pem}
embedded = json.dumps({"master": entry, "edge_lease": entry})

os.environ["FORGE_SDK_DEV"] = "1"
os.environ["FORGE_EMBEDDED_KEYS"] = embedded
from forge_verifier import deployment_fingerprint
fp = deployment_fingerprint()

now = datetime.datetime.now(datetime.timezone.utc)
payload = {
    "license_id": "terrane-dev-0001-2222-3333-444455556666",
    "cluster_id": "terrane-dev-cluster", "customer": "Terrane 联调客户",
    "product": "terrane", "active_from": now.isoformat(),
    "active_until": (now + datetime.timedelta(days=365)).isoformat(),
    "subscription": "Enterprise", "features": ["knowledge","agent","mcp","graph"],
    "mode": "offline", "binding": "hard", "bound_fingerprint": fp, "alg": "ed25519",
    "issuer": "forge-dev", "issued_at": now.isoformat(),
}
pb = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
blob = f"{b64u(pb)}.{b64u(priv.sign(pb))}"

# 写出联调资产
os.makedirs(".devkeys", exist_ok=True)
open(".devkeys/embedded_keys.json","w").write(embedded)
open(".devkeys/license.forge","w").write(blob)
open(".devkeys/fingerprint.txt","w").write(fp)
print("FINGERPRINT:", fp)
print("LICENSE_BLOB saved to .devkeys/license.forge (len", len(blob), ")")
