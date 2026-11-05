# Shared Git repository setup

The local Git repository is initialized on `main` with the initial commit. A GitHub remote still needs to be created under the team's chosen account or organization and made accessible to all six members. Once the destination is confirmed:

```powershell
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

Each member clones the remote, creates a short-lived feature branch, commits small changes, pushes the branch and opens a pull request. Protect `main` from direct pushes, require at least one peer review, and agree the checks before merging. Do not commit `.env`, keys or identifiable pilot data.

Before creating the remote, the team should confirm the GitHub account/organization owner and repository visibility. Private is a sensible default for a student team workspace; make sure collaborators can access it. The GitHub connection/CLI must be available to create it directly from Codex; until then, the local repo is ready to push.
