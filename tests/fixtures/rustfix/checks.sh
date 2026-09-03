#!/usr/bin/env bash
# Frozen instrument: run the test suite and clippy, print METRIC lines.
#
#   METRIC tests_passed=<n>      sum of "passed" over every "test result:" line
#   METRIC tests_failed=<n>      sum of "failed" over every test binary (no fail-fast);
#                                1 if the test build itself fails
#   METRIC clippy_warnings=<n>   lines containing "warning:" minus the summary
#                                lines; compile errors count too, so a crate that
#                                does not build is never reported as clean
#
# Always exits 0 so the harness can read the numbers when things are red. The
# raw cargo output goes to stderr.

cd "$(dirname "$0")" || exit 0

test_out=$(cargo test -q --no-fail-fast 2>&1)
test_rc=$?
printf '%s\n' "$test_out" >&2

passed=$(printf '%s\n' "$test_out" | grep -E '^test result:' \
    | sed -E 's/.* ([0-9]+) passed; ([0-9]+) failed;.*/\1/' | awk '{s+=$1} END {print s+0}')
failed=$(printf '%s\n' "$test_out" | grep -E '^test result:' \
    | sed -E 's/.* ([0-9]+) passed; ([0-9]+) failed;.*/\2/' | awk '{s+=$1} END {print s+0}')
if [ "$test_rc" -ne 0 ] && [ "$failed" -eq 0 ]; then
    failed=1
fi

clippy_out=$(cargo clippy -q --all-targets 2>&1)
clippy_rc=$?
printf '%s\n' "$clippy_out" >&2

warnings=$(printf '%s\n' "$clippy_out" | grep 'warning:' \
    | grep -Ev '^warning: `[^`]+` \([^)]*\) generated [0-9]+ warning' | wc -l | tr -d ' ')
if [ "$clippy_rc" -ne 0 ]; then
    errors=$(printf '%s\n' "$clippy_out" | grep -Ec '^error(\[[A-Z0-9]+\])?:' )
    warnings=$((warnings + errors))
fi

echo "METRIC tests_passed=$passed"
echo "METRIC tests_failed=$failed"
echo "METRIC clippy_warnings=$warnings"
exit 0
