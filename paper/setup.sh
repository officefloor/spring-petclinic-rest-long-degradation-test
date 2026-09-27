#!/usr/bin/env bash
#
# Install everything build.sh needs. Idempotent: re-running installs nothing
# that is already present at the right version.
#
# build.sh has two engine paths and this installs both, because they are not
# interchangeable:
#
#   pdflatex   The path that counts. arXiv compiles with pdflatex, and line 1 of
#              main.tex (\pdfoutput=1) is what selects it. Every figure here is a
#              PNG, which the latex + dvips route cannot read at all. Only this
#              path builds the file exactly as submitted. It comes from apt, so
#              it is the one step that needs root.
#
#   tectonic   The fallback. build.sh strips \pdfoutput=1 and compiles under it,
#              which checks structure, tables, floats, references and figure
#              paths, but is NOT a test of the submitted file. One static binary,
#              no sudo, no TeX tree to manage. Worth having even alongside
#              pdflatex: it is what a reviewer on a machine without root can run.
#
# This is deliberately separate from the repo's root setup.sh. That one builds
# the harness and its Python/Java measurement tooling. The paper is a different
# toolchain with a different audience, and neither needs the other installed.
#
# Environment:
#   SKIP_TEXLIVE=1      leave apt alone (no root, or TeX managed another way)
#   SKIP_TECTONIC=1     skip the fallback engine
#   PREFIX=<dir>        where tectonic is installed (default: $HOME/.local/bin)
#   TECTONIC_VERSION=x  install a different version; the sha256 pin is dropped
#
set -euo pipefail
cd "$(dirname "$0")"

PREFIX="${PREFIX:-$HOME/.local/bin}"
TECTONIC_VERSION_PINNED=0.17.0
TECTONIC_VERSION="${TECTONIC_VERSION:-$TECTONIC_VERSION_PINNED}"

# Not texlive-full (several GB). main.tex deliberately restricts itself to
# packages arXiv's own TeX Live already carries, and this set covers its
# preamble. Section 3 is the authority: if kpsewhich reports a missing .sty,
# add the package that owns it here rather than reaching for texlive-full.
# `apt-file search <name>.sty` names the owner.
TEX_PACKAGES=(
  texlive-latex-base        # pdflatex, and the core LaTeX packages
  texlive-latex-recommended # booktabs, caption, microtype, geometry
  texlive-latex-extra       # multirow, which is in none of the others
  texlive-fonts-recommended # the Type1 faces [T1]{fontenc} needs
  lmodern                   # \usepackage{lmodern}
)

# --no-install-recommends, which is the difference between 218MB and 846MB on
# Ubuntu 26.04. The recommends of these packages are documentation, extra font
# families and companion toolchains that main.tex does not load. Section 3
# proves the preamble still resolves, so the saving is not bought on trust.
APT_FLAGS=(--no-install-recommends)

# ---------------------------------------------------------------------------
# 1. pdflatex
# ---------------------------------------------------------------------------
echo "== 1/3  TeX Live (pdflatex) =="
if [ "${SKIP_TEXLIVE:-}" = 1 ]; then
  echo "   SKIP_TEXLIVE=1, skipped. build.sh will take the tectonic fallback."
elif ! command -v apt-get >/dev/null 2>&1; then
  if command -v pdflatex >/dev/null 2>&1; then
    echo "   no apt-get, but pdflatex is already here: $(pdflatex --version | head -1)"
    echo "   section 3 will say whether it carries main.tex's packages."
  else
    echo "   ! no apt-get on this system. Install a TeX distribution by hand:"
    echo "       macOS    brew install --cask mactex-no-gui   (or basictex)"
    echo "       Fedora   sudo dnf install texlive-scheme-medium"
    echo "       Arch     sudo pacman -S texlive-basic texlive-latexrecommended"
    echo "     then re-run. Or set SKIP_TEXLIVE=1 and build with tectonic only."
  fi
else
  # Asked per package, not by testing for pdflatex. A machine can have pdflatex
  # and still be missing a package the preamble needs, and that is exactly the
  # state a `command -v pdflatex` check would skip straight past.
  need=()
  for pkg in "${TEX_PACKAGES[@]}"; do
    if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null \
         | grep -q '^install ok installed$'; then
      need+=("$pkg")
    fi
  done

  if [ ${#need[@]} -eq 0 ]; then
    echo "   all ${#TEX_PACKAGES[@]} packages already installed: $(pdflatex --version | head -1)"
  else
    echo "   installing: ${need[*]}"
    echo "   ~218MB unpacked for the full set. This is the only step that needs"
    echo "   root, so sudo will ask."
    sudo apt-get update
    sudo apt-get install -y "${APT_FLAGS[@]}" "${need[@]}"
    echo "   installed: $(pdflatex --version | head -1)"
  fi
fi

# ---------------------------------------------------------------------------
# 2. tectonic
# ---------------------------------------------------------------------------
# sha256 of the upstream release tarball, per platform, pinned for the same
# reason tools/ck-sha256.txt is pinned in the root setup.sh: an unverified
# download of a build tool is not something to then execute. Upstream publishes
# no checksum file with the release, so these were taken from the 0.17.0
# tarballs on 2026-09-27 and must be recomputed when the pin moves.
echo
echo "== 2/3  tectonic (fallback engine) =="
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

TEC_TARGET=""
TEC_SHA=""
case "$(uname -s)/$(uname -m)" in
  Linux/x86_64)
    TEC_TARGET=x86_64-unknown-linux-musl
    TEC_SHA=8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7 ;;
  Linux/aarch64|Linux/arm64)
    TEC_TARGET=aarch64-unknown-linux-musl
    TEC_SHA=b10954a95404f3ab2328d2fa59a5ebab8e657f893fab096f98be8db7c0c979b8 ;;
esac

# An existing tectonic counts wherever it lives, so the check looks on PATH and
# in PREFIX both. PREFIX is often not yet on PATH the first time this is run.
TEC_BIN=""
if command -v tectonic >/dev/null 2>&1; then
  TEC_BIN="$(command -v tectonic)"
elif [ -x "$PREFIX/tectonic" ]; then
  TEC_BIN="$PREFIX/tectonic"
fi

if [ "${SKIP_TECTONIC:-}" = 1 ]; then
  echo "   SKIP_TECTONIC=1, skipped."
  TEC_BIN=""
elif [ -n "$TEC_BIN" ] \
     && "$TEC_BIN" --version 2>/dev/null | grep -q "Tectonic $TECTONIC_VERSION\$"; then
  echo "   already present: $("$TEC_BIN" --version) at $TEC_BIN"
elif [ -z "$TEC_TARGET" ]; then
  echo "   ! no pinned build for $(uname -s)/$(uname -m). Install it yourself:"
  echo "       macOS    brew install tectonic"
  echo "       cargo    cargo install tectonic"
  echo "     build.sh also honours TECTONIC=/path/to/tectonic."
else
  url="https://github.com/tectonic-typesetting/tectonic/releases/download"
  url="$url/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-${TEC_TARGET}.tar.gz"
  echo "   downloading tectonic $TECTONIC_VERSION ($TEC_TARGET)"
  curl -fsSL --retry 3 -o "$tmp/tectonic.tar.gz" "$url"

  if [ "$TECTONIC_VERSION" != "$TECTONIC_VERSION_PINNED" ]; then
    echo "   ! TECTONIC_VERSION overridden to $TECTONIC_VERSION; sha256 NOT checked"
  else
    got="$(sha256sum "$tmp/tectonic.tar.gz" | cut -d' ' -f1)"
    if [ "$got" != "$TEC_SHA" ]; then
      # Fail closed, like the CK download in the root setup.sh. A binary that is
      # not the pinned one does not get run here.
      echo "   ! sha256 MISMATCH for $url" >&2
      echo "     expected $TEC_SHA" >&2
      echo "     got      $got" >&2
      exit 1
    fi
    echo "   sha256 ok"
  fi

  tar xzf "$tmp/tectonic.tar.gz" -C "$tmp"
  mkdir -p "$PREFIX"
  install -m 755 "$tmp/tectonic" "$PREFIX/tectonic"
  TEC_BIN="$PREFIX/tectonic"
  echo "   installed $("$TEC_BIN" --version) to $TEC_BIN"
fi

# Tectonic ships no TeX tree. It fetches each file it needs from its web bundle
# on first use and caches it under ~/.cache/Tectonic. Prime that cache from
# main.tex's own preamble, so the first real build is not a surprise download,
# and so a later build survives being briefly offline. Driving it off main.tex
# rather than a package list copied into this script keeps it from drifting.
# Runs for an already-installed tectonic too, where it is a no-op once warm.
if [ -n "$TEC_BIN" ]; then
  {
    sed -n '/^\\documentclass/,/^\\begin{document}/p' main.tex
    # A body, because an empty one gives xdvipdfmx no page to convert and it
    # then fails the compile for a reason that has nothing to do with the cache.
    echo '\mbox{}'
    echo '\end{document}'
  } > "$tmp/prime.tex"
  if "$TEC_BIN" -X compile "$tmp/prime.tex" >/dev/null 2>&1; then
    echo "   package cache primed"
  else
    echo "   ! could not prime the cache; the first build will fetch the bundle instead"
  fi
fi

# ---------------------------------------------------------------------------
# 3. Verify
# ---------------------------------------------------------------------------
# Checked against main.tex's actual \usepackage lines rather than a list copied
# into this script, so it cannot drift when the preamble changes.
echo
echo "== 3/3  verifying main.tex's packages =="
if ! command -v kpsewhich >/dev/null 2>&1; then
  echo "   no kpsewhich (no TeX Live installed), so nothing to check."
  echo "   tectonic resolves its own packages from its bundle at build time."
else
  missing=()
  while read -r sty; do
    [ -n "$sty" ] || continue
    kpsewhich "${sty}.sty" >/dev/null 2>&1 || missing+=("$sty")
  done < <(sed -n 's/^\\usepackage\(\[[^]]*\]\)\?{\([^}]*\)}.*/\2/p' main.tex | tr ',' '\n')

  if [ ${#missing[@]} -eq 0 ]; then
    echo "   all present"
  else
    echo "   ! missing: ${missing[*]}"
    echo "     find the package that owns each with:  apt-file search <name>.sty"
    echo "     then add it to TEX_PACKAGES at the top of this script."
    exit 1
  fi
fi

echo
echo "Setup complete."
if ! command -v tectonic >/dev/null 2>&1 && [ -x "$PREFIX/tectonic" ]; then
  echo
  echo "NOTE: $PREFIX is not on this shell's PATH. On Ubuntu ~/.profile adds"
  echo "      ~/.local/bin at login, so a new shell will find it. Until then:"
  echo "        TECTONIC=$PREFIX/tectonic ./build.sh"
fi
echo
echo "Next:"
echo "  ./build.sh        # writes main.pdf and repacks arxiv.tar.gz"
if command -v pdflatex >/dev/null 2>&1; then
  echo "                    # pdflatex is present, so this builds the file as submitted"
else
  echo "                    # no pdflatex, so this is the tectonic verification build only"
fi
