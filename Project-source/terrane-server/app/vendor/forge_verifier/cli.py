"""forge-verify CLI — for product operators / support.

  forge-verify fingerprint            # print this host's deployment id (paste to vendor)
  forge-verify offline <blob|file>    # verify a .forge offline license against this host
"""

from __future__ import annotations

import sys

from forge_verifier import ForgeVerifier, deployment_fingerprint


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = args[0]
    if cmd == "fingerprint":
        print(deployment_fingerprint())
        return 0
    if cmd == "offline" and len(args) >= 2:
        blob = args[1]
        try:
            with open(blob, encoding="utf-8") as fh:
                blob = fh.read().strip()
        except OSError:
            pass
        v = ForgeVerifier().verify_offline(blob)
        print(f"status = {v.status}  reason = {v.reason}")
        if v.payload:
            print(f"product = {v.payload.get('product')}  until = {v.payload.get('active_until')}")
        if not v.unlocked:
            print(v.message("zh-CN"))
        return 0 if v.unlocked else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
