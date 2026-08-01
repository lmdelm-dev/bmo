#!/usr/bin/env bash
# BMO release helper
#
# After pushing + tagging (git push && git push --tags), run:
#   ./scripts/release.sh            # uses the latest git tag
#   ./scripts/release.sh v0.1.0     # or an explicit tag
#
# It downloads the GitHub tarball for that tag, computes its sha256 and fills
# the real checksums into Formula/bmo.rb and pkg/aur/PKGBUILD + .SRCINFO.
#
#   --check   verify the committed checksums match the tag (used by CI)
set -euo pipefail

REPO="${BMO_REPO:-https://github.com/lmdelm-dev/bmo}"
CHECK=""
if [ "${1:-}" = "--check" ]; then
    CHECK=1
    shift || true
fi

TAG="${1:-$(git describe --tags --abbrev=0 2>/dev/null || echo v0.1.0)}"
OWNER_REPO="${REPO#https://github.com/}"
OWNER_REPO="${OWNER_REPO%.git}"
TARBALL_URL="${BMO_TARBALL_URL:-https://codeload.github.com/${OWNER_REPO}/tar.gz/refs/tags/${TAG}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FORMULA="$ROOT_DIR/Formula/bmo.rb"
PKGBUILD="$ROOT_DIR/pkg/aur/PKGBUILD"
SRCINFO="$ROOT_DIR/pkg/aur/.SRCINFO"

echo "==> BMO release ${TAG}"
echo "    tarball: ${TARBALL_URL}"

TMP_TARBALL="$(mktemp)"
trap 'rm -f "$TMP_TARBALL"' EXIT
curl -fsSL "$TARBALL_URL" -o "$TMP_TARBALL"
SHA="$(sha256sum "$TMP_TARBALL" | awk '{print $1}')"
echo "    sha256: ${SHA}"

if [ -n "$CHECK" ]; then
    for f in "$FORMULA" "$PKGBUILD"; do
        if ! grep -q "$SHA" "$f"; then
            echo "ERROR: $f does not contain sha256 ${SHA} for tag ${TAG}" >&2
            echo "       run: ./scripts/release.sh ${TAG} && git add -A && git commit -m 'chore: update checksums' && git push" >&2
            exit 1
        fi
    done
    echo "==> checksums OK for ${TAG}"
    exit 0
fi

# Formula/bmo.rb
sed -i "s|sha256 \".*\"|sha256 \"${SHA}\"|" "$FORMULA"

# PKGBUILD
sed -i "s|sha256sums=('.*')|sha256sums=('${SHA}')|" "$PKGBUILD"

# .SRCINFO
sed -i "s|\tsha256sums = .*|\tsha256sums = ${SHA}|" "$SRCINFO"

echo "==> updated:"
grep -n "sha256" "$FORMULA"
grep -n "sha256sums" "$PKGBUILD"
grep -n "sha256sums" "$SRCINFO"
echo
echo "==> done. Review and commit the changes:"
echo "    git add Formula pkg && git commit -m 'chore: update v${TAG#v} checksums' && git push"
