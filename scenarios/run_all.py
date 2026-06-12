import a1_code_selfcheck
import a2_decomposition
import a3_budget_stop


def main() -> int:
    checks = [
        ("a1_code_selfcheck", a1_code_selfcheck.run),
        ("a2_decomposition", a2_decomposition.run),
        ("a3_budget_stop", a3_budget_stop.run),
    ]

    failed = False
    for name, check in checks:
        ok, reason = check()
        print(f"{name}: {'PASS' if ok else 'FAIL'} {reason}")
        if not ok:
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
