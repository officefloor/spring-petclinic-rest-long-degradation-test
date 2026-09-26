#!/usr/bin/env bash
#
# Host the metric-gallery figures on GitHub Pages, so a Blogger post can just
# link to them.
#
# The problem this solves: Blogger has no bulk image upload. Putting 101 figures
# in a post through the editor means 101 manual uploads, and the URLs it hands
# back are opaque, so a regenerated figure cannot replace an old one in place.
# Hosting the PNGs ourselves means the post body is generated text with stable
# URLs, and re-running the generator after a re-analysis updates every figure in
# every post at once without touching Blogger at all.
#
# How it works: an ORPHAN `gh-pages` branch holding nothing but `figs/`, built in
# a throwaway git worktree so your working tree is never touched. `blog/` is
# gitignored in this repo (see .gitignore), which is why the figures cannot
# simply be committed on main.
#
# Usage:
#   ./tools/gallery/publish_figs.sh              # build the branch locally only
#   ./tools/gallery/publish_figs.sh --push       # build it AND push to origin
#   ./tools/gallery/publish_figs.sh --push --branch gh-pages --prefix figs
#
# After the first push, enable Pages once: repo Settings -> Pages -> Source =
# "Deploy from a branch" -> branch `gh-pages`, folder `/ (root)`. It can take a
# minute or two to go live the first time.
#
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
FIGS="${REPO_ROOT}/blog/metric-gallery/figs"
BRANCH="gh-pages"
PREFIX="figs"
PUSH=0

while [ $# -gt 0 ]; do
  case "$1" in
    --push)   PUSH=1; shift ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    --figs)   FIGS="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done

if [ ! -d "$FIGS" ]; then
  echo "No figures at $FIGS" >&2
  echo "Generate them first:  python -m tools.gallery.metric_gallery" >&2
  exit 1
fi
COUNT=$(find "$FIGS" -name '*.png' | wc -l | tr -d ' ')
if [ "$COUNT" = 0 ]; then
  echo "No PNGs under $FIGS" >&2
  exit 1
fi

# A throwaway worktree, so nothing here can disturb the checkout you are working
# in. Removed on every exit path, including failure.
WT="$(mktemp -d)"
cleanup() {
  git -C "$REPO_ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
  rm -rf "$WT"
}
trap cleanup EXIT

if git -C "$REPO_ROOT" show-ref --quiet "refs/heads/${BRANCH}"; then
  echo "Using existing local branch ${BRANCH}"
  git -C "$REPO_ROOT" worktree add --quiet "$WT" "$BRANCH"
else
  echo "Creating orphan branch ${BRANCH}"
  git -C "$REPO_ROOT" worktree add --quiet --detach "$WT"
  git -C "$WT" checkout --quiet --orphan "$BRANCH"
  git -C "$WT" rm -rq --cached . 2>/dev/null || true
  find "$WT" -mindepth 1 -maxdepth 1 -not -name '.git' -exec rm -rf {} +
fi

mkdir -p "$WT/${PREFIX}"
# --delete so a metric removed from the catalogue stops being served. Without it
# the branch accumulates figures for metrics that no longer exist, and a stale
# post would keep rendering one.
rsync -a --delete --include='*.png' --exclude='*' "$FIGS/" "$WT/${PREFIX}/"

# .nojekyll: GitHub Pages runs Jekyll by default, which ignores paths starting
# with an underscore. Metric keys are snake_case and some could land there.
touch "$WT/.nojekyll"
cat > "$WT/index.html" <<'HTML'
<!doctype html>
<meta charset="utf-8">
<title>PetClinic-Evolve figures</title>
<p>Static image host for the metric gallery figures. See
<a href="https://blog.officefloor.net/">blog.officefloor.net</a>.</p>
HTML

git -C "$WT" add -A
if git -C "$WT" diff --cached --quiet; then
  echo "No change: ${BRANCH} already matches these ${COUNT} figures."
else
  git -C "$WT" commit -qm "Metric gallery figures (${COUNT} PNGs)"
  echo "Committed ${COUNT} figures on ${BRANCH}."
fi

ORIGIN="$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || true)"
SLUG="$(printf '%s' "$ORIGIN" | sed -e 's#^git@github.com:##' -e 's#^https://github.com/##' -e 's#\.git$##')"
OWNER="${SLUG%%/*}"
NAME="${SLUG##*/}"

if [ "$PUSH" = 1 ]; then
  if [ -z "$ORIGIN" ]; then
    echo "No 'origin' remote to push to." >&2
    exit 1
  fi
  echo "Pushing ${BRANCH} to ${ORIGIN}"
  git -C "$WT" push -u origin "$BRANCH"
else
  echo
  echo "Built locally only. Nothing was pushed. Re-run with --push to publish."
fi

if [ -n "$SLUG" ]; then
  BASE="https://${OWNER}.github.io/${NAME}/${PREFIX}/"
  echo
  echo "Base URL for the figures:"
  echo "  ${BASE}"
  echo
  echo "Now regenerate the Blogger fragments against it:"
  echo "  python -m tools.gallery.metric_gallery --no-figs --blogger \\"
  echo "      --img-base ${BASE}"
fi
