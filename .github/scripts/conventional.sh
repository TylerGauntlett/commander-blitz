#!/usr/bin/env bash
# Conventional-commit rules, in one place: the pull request gate (pr.yml), the
# ship decision on main (deploy.yml) and the /create-pr skill all call this.
#
# A squash merge's subject is its pull request's title, so the title's type is
# what decides whether a merge ships -- a site deploy and a Steam Deck release
# -- or lands quietly:
#
#   ships:          feat fix perf refactor build revert
#   does not ship:  docs chore ci test style
#
#   conventional.sh title "<title>"   exit 0 when the title is well formed
#   conventional.sh body <file>       exit 0 when the body follows the template
#   conventional.sh ships             subjects on stdin, one per line; prints
#                                     true when any of them ships
set -uo pipefail

SHIP_TYPES="feat fix perf refactor build revert"
QUIET_TYPES="docs chore ci test style"
MAX_TITLE=72

types_alt() { echo "$SHIP_TYPES $QUIET_TYPES" | tr ' ' '|'; }
quiet_alt() { echo "$QUIET_TYPES" | tr ' ' '|'; }

usage_types() {
  echo "  ships (site deploy + Steam Deck release): $SHIP_TYPES"
  echo "  does not ship:                            $QUIET_TYPES"
  echo "  form: type(scope): summary   -- scope optional, lowercase; '!' after it marks a breaking change"
}

check_title() {
  local t="$1" re
  re="^($(types_alt))(\([a-z0-9][a-z0-9-]*\))?!?: [^ ]"
  if ! [[ "$t" =~ $re ]]; then
    echo "title is not a conventional commit: \"$t\""
    usage_types
    return 1
  fi
  if [ "${#t}" -gt "$MAX_TITLE" ]; then
    echo "title is ${#t} characters; keep it to $MAX_TITLE so it reads whole in git log"
    return 1
  fi
  if [[ "$t" == *. ]]; then
    echo "title ends with a period; drop it"
    return 1
  fi
}

# The template in .github/pull_request_template.md, as required headings plus
# exactly one diagram. Prose quality is the reviewer's call, not this script's.
check_body() {
  local body h fail=0 diagrams
  # A body edited on github.com arrives with CRLF line endings.
  body=$(tr -d '\r' < "$1" 2>/dev/null)
  [ -n "${body//[[:space:]]/}" ] || { echo "the pull request body is empty; fill in .github/pull_request_template.md"; return 1; }
  for h in "## Risks" "## What" "## Why" "## How"; do
    grep -qxF "$h" <<<"$body" || { echo "body is missing the \"$h\" heading"; fail=1; }
  done
  grep -q '<details>' <<<"$body" || { echo "body is missing the collapsed <details> section"; fail=1; }
  # The template's own placeholders, left as they were.
  if grep -qxE -- '- *(Blast radius:|Rollback:)? *' <<<"$body" || grep -q '^One short paragraph:' <<<"$body"; then
    echo "body still has the template's empty bullets or placeholder summary; fill them in"; fail=1
  fi
  diagrams=$(grep -c '^```mermaid' <<<"$body")
  [ "$diagrams" = 1 ] || { echo "body has $diagrams mermaid diagrams; it needs exactly one"; fail=1; }
  return $fail
}

# Fails open: a subject that is not conventional (a direct push, history from
# before the gate) ships, and so does an empty list -- a lookup that failed is
# not "nothing to ship". Only a push made wholly of quiet types stays quiet.
ships() {
  local s seen=0 re
  re="^($(quiet_alt))(\([^)]*\))?: "
  while IFS= read -r s; do
    s="${s%$'\r'}"
    [ -n "$s" ] || continue
    seen=1
    [[ "$s" =~ $re ]] || { echo true; return; }
  done
  [ "$seen" = 1 ] && echo false || echo true
}

case "${1:-}" in
  title) check_title "${2:-}" ;;
  body) check_body "${2:-/dev/null}" ;;
  ships) ships ;;
  *) echo "usage: $0 title <title> | body <file> | ships < subjects" >&2; exit 2 ;;
esac
