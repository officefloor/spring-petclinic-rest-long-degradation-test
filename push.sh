#!/usr/bin/env bash
#
# Push each arm repo's evolve/<run_id>/... result branches to the fork on GitHub.
#
# The harness commits every chain's record onto its own
# evolve/<run_id>/<strategy>/<arm>/chain<n> branch in the arm repo but never pushes
# (the aggregate results/ CSV stays local and gitignored — see .gitignore). This
# script publishes those branches so each one is a self-contained remote record.
#
# Only branches that are MISSING or STALE on the remote are pushed; anything already
# published at the same sha is skipped. Pushes are fast-forward only — a diverged
# branch is reported and left alone rather than force-pushed.
#
# Usage:  ./push.sh [run_id] [--dry-run] [--all] [--allow-dirty]
#           run_id         only push evolve/<run_id>/... (default: every evolve branch)
#           --dry-run      list what would be pushed, push nothing
#           --all          also consider non-evolve local branches (e.g. the base refs)
#           --allow-dirty  push even if an arm worktree has uncommitted changes
#
# Overrides:  COMPARE_DIR=<path>   arm repo parent   (default ${HOME}/compare)
#             PUSH_URL=<git-url>   push target       (default: origin, rewritten to ssh)
#             PUSH_HTTPS=1         use origin's url as-is, no ssh rewrite
#
# Why the ssh rewrite: setup.sh clones over https, and an https origin has no stored
# credentials in a non-interactive shell ("could not read Username for
# 'https://github.com'"). ssh keys are already set up for the fork, so the default is
# to push to the ssh form of origin's url. PUSH_HTTPS=1 opts out.
#
set -euo pipefail

BASE="${COMPARE_DIR:-${HOME}/compare}"

RUN_ID="" DRY_RUN=0 ALL_BRANCHES=0 ALLOW_DIRTY=0
for a in "$@"; do
  case "$a" in
    --dry-run)     DRY_RUN=1 ;;
    --all)         ALL_BRANCHES=1 ;;
    --allow-dirty) ALLOW_DIRTY=1 ;;
    -h|--help)     sed -n '2,27p' "$0"; exit 0 ;;
    -*)            echo "unknown option: $a (see --help)" >&2; exit 2 ;;
    *)             [ -n "$RUN_ID" ] && { echo "only one run_id may be given" >&2; exit 2; }
                   RUN_ID="$a" ;;
  esac
done

# Which local refs are candidates. for-each-ref treats a pattern that ends at a slash
# boundary as a prefix, so refs/heads/evolve matches every nested chain branch.
if [ "$ALL_BRANCHES" = 1 ]; then
  [ -n "$RUN_ID" ] && { echo "--all and a run_id are mutually exclusive" >&2; exit 2; }
  REF_PATTERN="refs/heads"
elif [ -n "$RUN_ID" ]; then
  REF_PATTERN="refs/heads/evolve/$RUN_ID"
else
  REF_PATTERN="refs/heads/evolve"
fi

# https://github.com/o/r.git -> git@github.com:o/r.git  (see header)
to_ssh_url() {
  case "$1" in
    https://github.com/*) echo "git@github.com:${1#https://github.com/}" ;;
    *)                    echo "$1" ;;
  esac
}

total_pushed=0 total_skipped=0 total_diverged=0 dirty_seen=0 repos_seen=0

for arm in spring officefloor; do
  repo="$BASE/$arm"
  echo "== $arm  ($repo)"
  if [ ! -d "$repo/.git" ]; then
    echo "   not a git repo — skipped (run ./setup.sh first)"
    continue
  fi
  repos_seen=$((repos_seen + 1))

  if [ -n "${PUSH_URL:-}" ]; then
    url="$PUSH_URL"
  else
    url="$(git -C "$repo" remote get-url origin)"
    [ "${PUSH_HTTPS:-0}" = 1 ] || url="$(to_ssh_url "$url")"
  fi

  # A dirty worktree means the branch tip may not reflect the finished chain.
  while read -r wt; do
    [ -n "$wt" ] || continue
    [ -d "$wt" ] || continue
    if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]; then
      echo "   WARNING: uncommitted changes in $wt"
      dirty_seen=1
    fi
  done < <(git -C "$repo" worktree list --porcelain | awk '/^worktree /{print $2}')

  mapfile -t locals < <(git -C "$repo" for-each-ref \
      --format='%(objectname) %(refname:short)' --sort=refname "$REF_PATTERN")
  if [ "${#locals[@]}" -eq 0 ]; then
    echo "   no local branches under ${REF_PATTERN#refs/heads/}"
    continue
  fi

  # One network round-trip for the remote's current heads, rather than trusting
  # possibly-stale refs/remotes/origin/* (origin is https; we push over ssh).
  declare -A remote_sha=()
  while read -r sha ref; do
    [ -n "${sha:-}" ] || continue
    remote_sha["${ref#refs/heads/}"]="$sha"
  done < <(git ls-remote --heads "$url" 2>/dev/null)

  to_push=()
  for entry in "${locals[@]}"; do
    sha="${entry%% *}" branch="${entry#* }"
    rsha="${remote_sha[$branch]:-}"
    if [ -z "$rsha" ]; then
      to_push+=("$branch"); echo "   new     $branch"
    elif [ "$rsha" = "$sha" ]; then
      total_skipped=$((total_skipped + 1))
    elif git -C "$repo" merge-base --is-ancestor "$rsha" "$sha" 2>/dev/null; then
      to_push+=("$branch"); echo "   ahead   $branch"
    else
      total_diverged=$((total_diverged + 1))
      echo "   DIVERGED $branch — remote ${rsha:0:9} is not an ancestor; left alone" >&2
    fi
  done

  if [ "${#to_push[@]}" -eq 0 ]; then
    echo "   nothing to push (${total_skipped} already up to date)"
    continue
  fi

  if [ "$dirty_seen" = 1 ] && [ "$ALLOW_DIRTY" != 1 ]; then
    echo "   refusing to push with a dirty worktree — commit it, or pass --allow-dirty" >&2
    exit 1
  fi

  if [ "$DRY_RUN" = 1 ]; then
    echo "   [dry-run] would push ${#to_push[@]} branch(es) to $url"
  else
    echo "   pushing ${#to_push[@]} branch(es) to $url"
    git -C "$repo" push "$url" "${to_push[@]}"
    # origin is https and may never be fetched from; update its remote-tracking refs
    # from the same url we pushed to so `git branch -vv` reflects reality.
    git -C "$repo" fetch --quiet "$url" \
        "+refs/heads/*:refs/remotes/origin/*" 2>/dev/null || true
  fi
  total_pushed=$((total_pushed + ${#to_push[@]}))
done

echo
[ "$repos_seen" -gt 0 ] || { echo "No arm repos under $BASE — run ./setup.sh first." >&2; exit 1; }
prefix=""; [ "$DRY_RUN" = 1 ] && prefix="[dry-run] "
echo "${prefix}${total_pushed} branch(es) pushed, ${total_skipped} already up to date, ${total_diverged} diverged."
[ "$total_diverged" -gt 0 ] && echo "Diverged branches were NOT force-pushed; resolve them by hand." >&2
exit 0
