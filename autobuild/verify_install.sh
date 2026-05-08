#!/usr/bin/env bash
# verify_install.sh — Release-readiness gate for PyAutoLens.
#
# Runs a suite of independent install-path checks (see verify_install.md for
# the full description of each check):
#
#   A  pip install autolens (default Python) + start_here.py + welcome.py
#   B  pip install autolens succeeds + imports on python3.9 / 3.10 / 3.11 / 3.13
#   C  conda install flow (python=3.12) + start_here.py + welcome.py
#   D  pip install "autolens[optional]" resolves
#   E  pip install autolens==2026.2.26.4 still installs by explicit pin
#
# Each check creates its own throwaway venv / conda env and reports
# PASS / FAIL / SKIP. A failed check never aborts the suite. Cleanup runs at
# the end (use --keep to retain artefacts for inspection).
#
# Usage:
#   verify_install                       # run all checks
#   verify_install A                     # run a single check
#   verify_install A C E                 # run a subset
#   verify_install --version 2026.4.5.2  # pin a specific PyPI version (A/C/D)
#   verify_install --keep                # don't clean up at the end
#   verify_install -h | --help

set -uo pipefail   # NB: no -e — checks must continue past expected failures.

# Unset PYTHONPATH so checks aren't shadowed by user-side editable installs.
# When the calling shell exports PYTHONPATH=/path/to/PyAutoConf:/path/to/...
# (a common setup when developing the libs), throwaway venvs created here
# will still resolve `import autolens` etc. from those local source dirs
# rather than from the just-installed PyPI artefacts. That defeats the
# purpose of testing the install path. Clearing PYTHONPATH for the script
# (and every subshell it spawns) keeps each venv truly isolated.
unset PYTHONPATH

# ----- usage -----

usage() {
    cat <<'USAGE'
verify_install — release-readiness gate for PyAutoLens.

Usage:
  verify_install [CHECKS...] [--version VERSION] [--keep] [-h]

Checks:
  A   pip install autolens (default python3) + start_here.py + welcome.py
  B   pip install autolens succeeds + imports on python3.9, 3.10, 3.11, 3.13
  C   conda install flow (python=3.12) + start_here.py + welcome.py
  D   pip install "autolens[optional]" resolves and imports
  E   pip install autolens==2026.2.26.4 (yanked) installs by explicit pin

Default: run all checks.

Options:
  --version VERSION   Pin a specific PyPI version (applies to A, C, D).
  --keep              Don't clean up venvs / conda envs / clones at the end.
  -h, --help          Show this help.
USAGE
}

# ----- argument parsing -----

TARGET_VERSION=""
KEEP=0
REQUESTED_CHECKS=()

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --version)
            if [ $# -lt 2 ]; then
                echo "verify_install: --version requires a value" >&2
                exit 2
            fi
            TARGET_VERSION="$2"
            shift 2
            ;;
        --keep)
            KEEP=1
            shift
            ;;
        A|B|C|D|E|all)
            REQUESTED_CHECKS+=("$1")
            shift
            ;;
        *)
            echo "verify_install: unknown argument '$1'" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ ${#REQUESTED_CHECKS[@]} -eq 0 ]; then
    REQUESTED_CHECKS=(all)
fi

# Expand "all" into A B C D E.
SELECTED=()
for c in "${REQUESTED_CHECKS[@]}"; do
    if [ "$c" = "all" ]; then
        SELECTED=(A B C D E)
        break
    fi
    SELECTED+=("$c")
done

# ----- shared state -----

TS=$(date +%Y%m%d_%H%M%S)
RESULTS=()       # each row "LETTER|STATUS|DETAIL"
RESULTS_LOG=""   # captured tail appended below the table on FAIL
ARTEFACTS=()     # paths to rm -rf at end
CONDA_ENVS=()    # conda env names to remove at end

PIP_INSTALL_TARGET="autolens"
PIP_INSTALL_OPTIONAL="autolens[optional]"
if [ -n "$TARGET_VERSION" ]; then
    PIP_INSTALL_TARGET="autolens==$TARGET_VERSION"
    PIP_INSTALL_OPTIONAL="autolens[optional]==$TARGET_VERSION"
fi

# ----- helpers -----

# step <message>: print an indented sub-step header with elapsed time.
step() {
    local now
    now=$(date +%H:%M:%S)
    printf '  [%s] -> %s\n' "$now" "$1"
}

# tail_log <header> <text>: append a labelled output tail to RESULTS_LOG.
tail_log() {
    local header="$1"
    local text="$2"
    RESULTS_LOG+=$'\n--- '"$header"$' ---\n'"$(printf '%s' "$text" | tail -40)"$'\n'
}

# make_venv <venv-path> <python-bin>: create a venv. Returns 0 on success.
make_venv() {
    local venv_path="$1"
    local pybin="$2"
    "$pybin" -m venv "$venv_path"
}

# ----- check A: pip install on default python -----

check_a() {
    echo
    echo "=== Check A: pip install + start_here.py + welcome.py ==="

    local venv="/tmp/autolens_verify_A_$TS"
    local workspace="/tmp/autolens_workspace_verify_A_$TS"
    ARTEFACTS+=("$venv" "$workspace")

    step "creating venv with python3 at $venv"
    if ! make_venv "$venv" python3; then
        RESULTS+=("A|FAIL|could not create venv with python3")
        return
    fi

    # shellcheck source=/dev/null
    source "$venv/bin/activate"

    step "upgrading pip"
    pip install --upgrade pip

    step "pip install $PIP_INSTALL_TARGET"
    if ! pip install "$PIP_INSTALL_TARGET" |& tee /tmp/A_pip.log; then
        RESULTS+=("A|FAIL|pip install $PIP_INSTALL_TARGET failed")
        tail_log "Check A pip output" "$(cat /tmp/A_pip.log 2>/dev/null)"
        deactivate
        return
    fi

    step "pip install numba"
    pip install numba |& tee /tmp/A_numba.log

    step "showing installed versions"
    python -c "
import autolens, autogalaxy, autoarray, autofit, autoconf
print(f'autolens:   {autolens.__version__}')
print(f'autogalaxy: {autogalaxy.__version__}')
print(f'autoarray:  {autoarray.__version__}')
print(f'autofit:    {autofit.__version__}')
print(f'autoconf:   {autoconf.__version__}')
"

    step "cloning autolens_workspace"
    if ! git clone --depth 1 \
            https://github.com/Jammy2211/autolens_workspace.git "$workspace"; then
        RESULTS+=("A|FAIL|workspace clone failed")
        deactivate
        return
    fi

    local sh_rc=0 wc_rc=0
    step "running start_here.py (PYAUTO_TEST_MODE=1)"
    (cd "$workspace" && PYAUTO_TEST_MODE=1 JAX_ENABLE_X64=True \
        python start_here.py) |& tee /tmp/A_sh.log
    sh_rc=${PIPESTATUS[0]}

    step "running welcome.py (PYAUTO_TEST_MODE=1)"
    (cd "$workspace" && PYAUTO_TEST_MODE=1 JAX_ENABLE_X64=True \
        python welcome.py) |& tee /tmp/A_wc.log
    wc_rc=${PIPESTATUS[0]}

    deactivate

    if [ "$sh_rc" -eq 0 ] && [ "$wc_rc" -eq 0 ]; then
        RESULTS+=("A|PASS|pip install + start_here.py + welcome.py")
    else
        RESULTS+=("A|FAIL|start_here rc=$sh_rc welcome rc=$wc_rc")
        [ "$sh_rc" -ne 0 ] && tail_log "Check A start_here.py output" "$(cat /tmp/A_sh.log 2>/dev/null)"
        [ "$wc_rc" -ne 0 ] && tail_log "Check A welcome.py output"    "$(cat /tmp/A_wc.log 2>/dev/null)"
    fi
}

# ----- check B: install + import on every supported python version -----
#
# requires-python = ">=3.9", classifiers cover 3.9–3.13. 3.12 / 3.13 are the
# recommended versions; 3.9 / 3.10 / 3.11 print a loud (bypassable) banner on
# autoconf import. Check B confirms install + import works on each of
# 3.9 / 3.10 / 3.11 / 3.13. Check A covers the recommended-default-python
# path with full workspace script execution (typically python3 = 3.12).

check_b_one() {
    local pybin="$1"
    local label="${pybin#python}"

    if ! command -v "$pybin" > /dev/null 2>&1; then
        step "$pybin not installed — SKIP"
        RESULTS+=("B|SKIP|$pybin not installed")
        return
    fi

    local venv="/tmp/autolens_verify_B_${label}_$TS"
    ARTEFACTS+=("$venv")

    step "$pybin: creating venv at $venv"
    if ! make_venv "$venv" "$pybin"; then
        RESULTS+=("B|FAIL|$pybin could not create venv")
        return
    fi

    # shellcheck source=/dev/null
    source "$venv/bin/activate"
    pip install --upgrade pip > /dev/null 2>&1 || true

    step "$pybin: pip install $PIP_INSTALL_TARGET"
    local pip_out pip_rc=0
    pip_out=$(pip install "$PIP_INSTALL_TARGET" 2>&1) || pip_rc=$?

    if [ "$pip_rc" -ne 0 ]; then
        RESULTS+=("B|FAIL|$pybin pip install failed (rc=$pip_rc)")
        tail_log "Check B ($pybin) pip output" "$pip_out"
        deactivate
        return
    fi

    step "$pybin: importing autolens, autogalaxy, autoarray, autofit, autoconf"
    local import_out import_rc=0
    import_out=$(python -c "
import autolens, autogalaxy, autoarray, autofit, autoconf
print(f'autolens={autolens.__version__}')
" 2>&1) || import_rc=$?
    deactivate

    printf '%s\n' "$import_out" | sed 's/^/      /'

    if [ "$import_rc" -ne 0 ]; then
        RESULTS+=("B|FAIL|$pybin import failed (rc=$import_rc)")
        tail_log "Check B ($pybin) import output" "$import_out"
        return
    fi

    # Soft banner check on non-recommended versions (3.9 / 3.10 / 3.11).
    # The banner copy may evolve, so banner-missing is reported in the detail
    # line but does not flip PASS to FAIL.
    local detail="$pybin install + import OK"
    case "$label" in
        3.9|3.10|3.11)
            if printf '%s' "$import_out" | grep -qiE "recommended.*python|python.*version.*recommend"; then
                detail="$detail (banner present)"
            else
                detail="$detail (no banner detected)"
            fi
            ;;
    esac
    RESULTS+=("B|PASS|$detail")
}

check_b() {
    echo
    echo "=== Check B: install + import on python3.9 / 3.10 / 3.11 / 3.13 ==="
    check_b_one python3.9
    check_b_one python3.10
    check_b_one python3.11
    check_b_one python3.13
}

# ----- check C: conda flow -----

check_c() {
    echo
    echo "=== Check C: conda install flow ==="

    if ! command -v conda > /dev/null 2>&1; then
        step "conda not on PATH — SKIP"
        RESULTS+=("C|SKIP|conda not on PATH")
        return
    fi

    local env_name="autolens_verify_$TS"
    local workspace="/tmp/autolens_workspace_verify_C_$TS"
    CONDA_ENVS+=("$env_name")
    ARTEFACTS+=("$workspace")

    step "conda create -n $env_name python=3.12"
    if ! conda create -y -n "$env_name" python=3.12 |& tee /tmp/C_create.log; then
        RESULTS+=("C|FAIL|conda create failed")
        tail_log "Check C conda create output" "$(cat /tmp/C_create.log 2>/dev/null)"
        return
    fi

    step "upgrading pip in $env_name"
    conda run -n "$env_name" pip install --upgrade pip

    step "conda pip install $PIP_INSTALL_TARGET --no-cache-dir"
    if ! conda run -n "$env_name" pip install "$PIP_INSTALL_TARGET" --no-cache-dir \
            |& tee /tmp/C_pip.log; then
        RESULTS+=("C|FAIL|conda pip install $PIP_INSTALL_TARGET failed")
        tail_log "Check C pip output" "$(cat /tmp/C_pip.log 2>/dev/null)"
        return
    fi

    step "conda pip install numba --no-cache-dir"
    conda run -n "$env_name" pip install numba --no-cache-dir |& tee /tmp/C_numba.log

    step "cloning autolens_workspace"
    if ! git clone --depth 1 \
            https://github.com/Jammy2211/autolens_workspace.git "$workspace"; then
        RESULTS+=("C|FAIL|workspace clone failed")
        return
    fi

    local sh_rc=0 wc_rc=0
    step "conda run welcome.py (PYAUTO_TEST_MODE=1)"
    (cd "$workspace" && conda run -n "$env_name" \
        env PYAUTO_TEST_MODE=1 JAX_ENABLE_X64=True python welcome.py) |& tee /tmp/C_wc.log
    wc_rc=${PIPESTATUS[0]}

    step "conda run start_here.py (PYAUTO_TEST_MODE=1)"
    (cd "$workspace" && conda run -n "$env_name" \
        env PYAUTO_TEST_MODE=1 JAX_ENABLE_X64=True python start_here.py) |& tee /tmp/C_sh.log
    sh_rc=${PIPESTATUS[0]}

    if [ "$sh_rc" -eq 0 ] && [ "$wc_rc" -eq 0 ]; then
        RESULTS+=("C|PASS|conda(python=3.12) + start_here + welcome")
    else
        RESULTS+=("C|FAIL|start_here rc=$sh_rc welcome rc=$wc_rc")
        [ "$sh_rc" -ne 0 ] && tail_log "Check C start_here.py output" "$(cat /tmp/C_sh.log 2>/dev/null)"
        [ "$wc_rc" -ne 0 ] && tail_log "Check C welcome.py output"    "$(cat /tmp/C_wc.log 2>/dev/null)"
    fi
}

# ----- check D: optional extra resolves -----

check_d() {
    echo
    echo "=== Check D: pip install \"$PIP_INSTALL_OPTIONAL\" ==="

    local venv="/tmp/autolens_verify_D_$TS"
    ARTEFACTS+=("$venv")

    step "creating venv with python3 at $venv"
    if ! make_venv "$venv" python3; then
        RESULTS+=("D|FAIL|could not create venv with python3")
        return
    fi

    # shellcheck source=/dev/null
    source "$venv/bin/activate"
    pip install --upgrade pip > /dev/null 2>&1

    step "pip install $PIP_INSTALL_OPTIONAL"
    pip install "$PIP_INSTALL_OPTIONAL" |& tee /tmp/D_pip.log
    local pip_rc=${PIPESTATUS[0]}

    step "import autolens"
    local import_rc=0
    python -c "import autolens; print(autolens.__version__)" || import_rc=$?
    deactivate

    if [ "$pip_rc" -eq 0 ] && [ "$import_rc" -eq 0 ]; then
        RESULTS+=("D|PASS|$PIP_INSTALL_OPTIONAL resolved + imports")
    else
        RESULTS+=("D|FAIL|pip rc=$pip_rc import rc=$import_rc")
        tail_log "Check D output" "$(cat /tmp/D_pip.log 2>/dev/null)"
    fi
}

# ----- check E: yanked-pin -----

check_e() {
    echo
    echo "=== Check E: pip install autolens==2026.2.26.4 (yanked) ==="

    local venv="/tmp/autolens_verify_E_$TS"
    ARTEFACTS+=("$venv")

    step "creating venv with python3 at $venv"
    if ! make_venv "$venv" python3; then
        RESULTS+=("E|FAIL|could not create venv with python3")
        return
    fi

    # shellcheck source=/dev/null
    source "$venv/bin/activate"
    pip install --upgrade pip > /dev/null 2>&1

    # Pin all 5 PyAuto libs together — pinning only autolens lets pip resolve
    # autogalaxy/autofit/autoarray to latest, which can break the autolens
    # 2026.2.26.4 import path (e.g. ModuleNotFoundError on a renamed/removed
    # symbol in autogalaxy 2026.5.1.4). Same multi-pin pattern that release.yml
    # uses (lines 130-138).
    step "pip install autoconf/autoarray/autofit/autogalaxy/autolens==2026.2.26.4"
    pip install \
      autoconf==2026.2.26.4 \
      autoarray==2026.2.26.4 \
      autofit==2026.2.26.4 \
      autogalaxy==2026.2.26.4 \
      autolens==2026.2.26.4 |& tee /tmp/E_pip.log
    local pip_rc=${PIPESTATUS[0]}

    # Verify pip install resolved + downloaded all 5 wheels (i.e. yanked
    # version is still reachable via explicit pin). We deliberately do NOT
    # exercise `import autolens` here: yanked versions are typically yanked
    # because of bugs, and 2026.2.26.4 specifically has an import-time
    # autoconf config-key lookup that fails standalone — exactly the kind
    # of issue that justified yanking it. Check E's purpose is to verify
    # the install path (resolve + download), not runtime correctness.
    local installed_pkgs=""
    if [ "$pip_rc" -eq 0 ]; then
        step "verifying all 5 libs installed at 2026.2.26.4"
        installed_pkgs=$(pip list --format=freeze 2>/dev/null | grep -E "^(autoconf|autoarray|autofit|autogalaxy|autolens)==" | sort | tr '\n' ' ')
        echo "      $installed_pkgs"
    fi
    deactivate

    # PASS if pip succeeded AND all 5 libs report version 2026.2.26.4 from `pip list`.
    local expected_count=5
    local actual_count
    actual_count=$(printf '%s' "$installed_pkgs" | grep -oE "==2026.2.26.4" | wc -l)
    if [ "$pip_rc" -eq 0 ] && [ "$actual_count" -eq "$expected_count" ]; then
        RESULTS+=("E|PASS|all 5 libs installed at 2026.2.26.4 via explicit pin")
    else
        RESULTS+=("E|FAIL|pip rc=$pip_rc, $actual_count/$expected_count libs at 2026.2.26.4")
        tail_log "Check E output" "$(cat /tmp/E_pip.log 2>/dev/null)"
    fi
}

# ----- runner -----

START_TS=$(date +%H:%M:%S)
echo "verify_install starting at $START_TS — running checks: ${SELECTED[*]}"

for letter in "${SELECTED[@]}"; do
    case "$letter" in
        A) check_a ;;
        B) check_b ;;
        C) check_c ;;
        D) check_d ;;
        E) check_e ;;
        *) echo "verify_install: unknown check '$letter'" >&2 ;;
    esac
done

# ----- report -----

echo
echo "Install Verification Results"
echo "============================"
printf '%-5s  %-6s  %s\n' "Check" "Status" "Detail"
printf '%-5s  %-6s  %s\n' "-----" "------" "------"

n_fail=0
n_skip=0
for row in "${RESULTS[@]}"; do
    IFS='|' read -r letter status detail <<< "$row"
    printf '%-5s  %-6s  %s\n' "$letter" "$status" "$detail"
    [ "$status" = "FAIL" ] && n_fail=$((n_fail + 1))
    [ "$status" = "SKIP" ] && n_skip=$((n_skip + 1))
done

echo
if [ "$n_fail" -eq 0 ]; then
    echo "Overall: PASS ($n_skip skipped)"
else
    echo "Overall: FAIL ($n_fail failure(s), $n_skip skipped)"
fi

if [ -n "$RESULTS_LOG" ]; then
    echo
    echo "----- Failure detail -----"
    printf '%s\n' "$RESULTS_LOG"
fi

# ----- cleanup -----

if [ "$KEEP" -eq 1 ]; then
    echo
    echo "--keep: artefacts retained:"
    for p in "${ARTEFACTS[@]}"; do echo "  $p"; done
    for n in "${CONDA_ENVS[@]}"; do echo "  conda env: $n"; done
else
    echo
    echo "Cleaning up artefacts (use --keep next time to retain)..."
    for p in "${ARTEFACTS[@]}"; do
        rm -rf "$p"
    done
    for n in "${CONDA_ENVS[@]}"; do
        conda env remove -y -n "$n" > /dev/null 2>&1 || true
    done
fi

[ "$n_fail" -eq 0 ]
