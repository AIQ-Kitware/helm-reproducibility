from __future__ import annotations

import argparse
import shutil

from helm_audit.infra.env import load_env
from helm_audit.infra.plotly_env import has_plotly_static_dependencies


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate helm_audit environment.")
    parser.add_argument("--require-precomputed-root", action="store_true")
    parser.add_argument("--require-plotly-static", action="store_true")
    parser.add_argument(
        "--plotly-static-only",
        action="store_true",
        help="Only validate plotly/kaleido/chrome static rendering dependencies.",
    )
    args = parser.parse_args(argv)

    if args.plotly_static_only:
        ok, missing = has_plotly_static_dependencies()
        if not ok:
            raise SystemExit(
                "plotly static rendering is not ready; missing: "
                + ", ".join(missing)
            )
        print("plotly static rendering looks good.")
        return

    env = load_env()
    required = {
        "AIQ_MAGNET_ROOT": env.aiq_magnet_root,
        "AUDIT_RESULTS_ROOT": env.audit_results_root,
    }
    if args.require_precomputed_root:
        required["HELM_PRECOMPUTED_ROOT"] = env.helm_precomputed_root
    for key, path in required.items():
        if not path.exists():
            raise SystemExit(f"{key} does not exist: {path}")
    for exe in ["kwdagger", "helm-run", env.aiq_python]:
        if shutil.which(exe) is None:
            raise SystemExit(f"required executable not found: {exe}")
    if args.require_plotly_static:
        ok, missing = has_plotly_static_dependencies()
        if not ok:
            raise SystemExit(
                "plotly static rendering is not ready; missing: "
                + ", ".join(missing)
            )
    print("helm_audit environment looks good.")


if __name__ == "__main__":
    main()
