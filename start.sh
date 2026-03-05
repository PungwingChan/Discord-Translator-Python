PIP_DIR="$(dirname "$0")/.cache/pip"
mkdir -p "$PIP_DIR"

echo "[DEP ] Checking dependencies..."
python3 -m pip install \
    --target "$PIP_DIR" \
    --quiet \
    -i https://mirror.kakao.com/pypi/simple \
    requests flask "discord.py>=2.0"
echo "[DEP ] Done."
