# .github/workflows/prayer.yml
#
# Started by the "Add a request" form on the prayer list page. Adds the
# request to the top of prayer.txt (python3 prayer.py add), saves it to
# main, then starts "Build and deploy" so it shows up on the site.
#
# The form can start this because the page carries the PRAYER_TOKEN
# secret (see prayer.py). If the form ever stops working, check the
# Actions tab for a red run of this workflow.
#
# The request comes in through env: below, never pasted into the
# commands, so nothing anyone types can run as a command.

name: Add prayer request

on:
  workflow_dispatch:
    inputs:
      text:
        description: The request
        required: true
        type: string
      name:
        description: Who asked (optional)
        required: false
        type: string
        default: ''
      date:
        description: The date on their phone, like 2026-09-23 (optional)
        required: false
        type: string
        default: ''

permissions:
  contents: write   # save prayer.txt
  actions: write    # start Build and deploy

jobs:
  add:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4

      - name: Add the request to prayer.txt
        env:
          PR_TEXT: ${{ inputs.text }}
          PR_NAME: ${{ inputs.name }}
          PR_DATE: ${{ inputs.date }}
        run: |
          git config user.name "Grace House website"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          # If two people send at the same moment, one save gets turned
          # away. Start over from the newest prayer.txt and try again,
          # after a random pause so they don't collide again.
          for try in 1 2 3 4 5 6 7 8 9 10; do
            git fetch --quiet origin main
            git reset --quiet --hard origin/main
            python3 prayer.py add || exit 1
            git add prayer.txt
            git commit --quiet -m "Prayer request from the website"
            if git push --quiet origin HEAD:main; then exit 0; fi
            echo "prayer.txt changed at the same moment; trying again."
            sleep $((RANDOM % 6 + try))
          done
          echo "::error::Couldn't save the request after 10 tries."
          exit 1

      # Saves made by an Action don't set off other Actions, so start the
      # site build by hand. It picks up every request saved so far.
      - name: Rebuild the site
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh workflow run deploy.yml --repo "${{ github.repository }}" --ref main
