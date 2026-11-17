#!/bin/sh
# Publishes today's /api/live + /api/health to the live-data branch (one commit, force-pushed), which redeploys the
# public map on GitHub Pages. Runs daily at 08:00 (waterways-publish.timer), after the 07:20 collector.
# Push auth: the gh CLI login of this user (gh auth git-credential), no token in this file.
set -eu
D=/home/emir/waterways-live
API=http://127.0.0.1:8796
if [ ! -d "$D/.git" ]; then
  git init -q -b live-data "$D"
  git -C "$D" remote add origin https://github.com/vulevu228/InfectedWaterways.git
  git -C "$D" config credential.helper '!gh auth git-credential'
  git -C "$D" config user.name "vulevu228"
  git -C "$D" config user.email "vulevu228@users.noreply.github.com"
fi
cd "$D"
for f in live health; do
  curl -sf -m 120 "$API/api/$f" -o "$f.json.tmp"
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert not d.get('error'), d.get('error')" "$f.json.tmp"
  mv "$f.json.tmp" "$f.json"
done
printf 'Daily snapshot of the Infected Waterways API for the public map. Overwritten every day; see main for the code.\n' > README.md
git add live.json health.json README.md
msg="Live snapshot $(date -u +%Y-%m-%dT%H:%MZ)"
git commit -q --amend -m "$msg" 2>/dev/null || git commit -q -m "$msg"
git push -q -f origin live-data
# a push to live-data does not start the Pages workflow (it only lives on main), so start it here
gh workflow run pages.yml --repo vulevu228/InfectedWaterways --ref main
echo "published: $msg (Pages deploy started)"
