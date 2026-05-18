#!/bin/bash

crimson_script_dir() {
  cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

crimson_root_dir() {
  if [ -n "${CRIMSON_ROOT:-}" ]; then
    printf '%s\n' "$CRIMSON_ROOT"
    return 0
  fi

  local script_dir
  script_dir="$(crimson_script_dir)"
  cd "$script_dir/.." && pwd
}

crimson_default_venv_dir() {
  local root_dir
  root_dir="$(crimson_root_dir)"
  printf '%s\n' "$root_dir/farm-ng-amiga/BYU_Amiga/amiga-env"
}

crimson_python_bin() {
  if [ -n "${CRIMSON_PYTHON:-}" ]; then
    if [ -x "${CRIMSON_PYTHON}" ]; then
      printf '%s\n' "${CRIMSON_PYTHON}"
      return 0
    fi

    echo "CRIMSON_PYTHON is set but not executable: ${CRIMSON_PYTHON}" >&2
    return 1
  fi

  local root_dir
  local venv_python
  root_dir="$(crimson_root_dir)"
  venv_python="$root_dir/farm-ng-amiga/BYU_Amiga/amiga-env/bin/python"
  if [ -x "$venv_python" ]; then
    printf '%s\n' "$venv_python"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  echo "Unable to find python3. Install Python 3 or set CRIMSON_PYTHON." >&2
  return 1
}

crimson_activate_venv() {
  local venv_dir
  venv_dir="${CRIMSON_VENV_DIR:-$(crimson_default_venv_dir)}"
  if [ ! -f "$venv_dir/bin/activate" ]; then
    echo "Expected a virtual environment at $venv_dir. Run scripts/bootstrap_local_dev.sh first." >&2
    return 1
  fi

  # shellcheck disable=SC1090
  source "$venv_dir/bin/activate"
}
