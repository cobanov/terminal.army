#!/usr/bin/env bash
# terminal.army — tek komutluk kurulum (uv + tarmy)
#
# Kullanim (public repo):
#   curl -fsSL https://raw.githubusercontent.com/cobanov/terminal.army/main/scripts/install.sh | sh
#
# Kullanim (private repo, SSH ile):
#   OGAME_REPO="git+ssh://git@github.com/cobanov/terminal.army.git" sh install.sh
#
# Env override:
#   OGAME_REPO  : git URL (default: HTTPS public repo URL)
#   OGAME_REF   : git ref (branch/tag, default: main)
#   OGAME_PY    : Python version (default: 3.12)

set -eu

OGAME_REPO="${OGAME_REPO:-git+https://github.com/cobanov/terminal.army.git}"
OGAME_REF="${OGAME_REF:-main}"
OGAME_PY="${OGAME_PY:-3.12}"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
red() { printf "\033[31m%s\033[0m\n" "$*" >&2; }

bold "Sakusen 策戦 · install"
echo "  repo : $OGAME_REPO"
echo "  ref  : $OGAME_REF"
echo "  py   : $OGAME_PY"
echo

# 1. uv kurulu mu? Degilse kur.
if ! command -v uv >/dev/null 2>&1; then
    yellow "uv bulunamadi, kuruluyor..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # PATH'a ekle (mevcut shell icin)
    if [ -d "$HOME/.local/bin" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    fi
    if [ -d "$HOME/.cargo/bin" ]; then
        export PATH="$HOME/.cargo/bin:$PATH"
    fi
fi

if ! command -v uv >/dev/null 2>&1; then
    red "uv kuruldu ama PATH'da bulunamiyor. Yeni terminal acip tekrar dene."
    exit 1
fi

bold "uv version: $(uv --version)"

# 2. Python varsa kullan, yoksa indir
uv python install "$OGAME_PY" >/dev/null 2>&1 || true

# 3. sakusen'i tool olarak kur
bold "sakusen kuruluyor..."
uv tool install --reinstall --python "$OGAME_PY" "${OGAME_REPO}@${OGAME_REF}"

# 4. PATH guvencesi
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *)
        yellow "Not: ~/.local/bin PATH'inda gorunmuyor. ~/.bashrc veya ~/.zshrc'a ekle:"
        echo '  export PATH="$HOME/.local/bin:$PATH"'
        ;;
esac

echo
green "✓ Kurulum tamam."
echo
echo "Oynamaya basla:"
echo "  sakusen                                       # solo (yerel SQLite)"
echo "  SAKUSEN_BACKEND=https://sakusen.space sakusen # multiplayer"
echo "  sakusen-server                                # multiplayer host"
echo
echo "Daha fazlasi icin: sakusen --help"
