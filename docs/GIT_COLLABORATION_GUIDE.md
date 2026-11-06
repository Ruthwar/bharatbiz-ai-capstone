# BharatBiz AI Capstone: Git Collaboration Guide

This guide explains how team members can download the repository, pull the latest code, add changes, commit them, and submit them for review.

## Team workflow at a glance

- All collaborators can read the private repository and its `main` branch.
- Each member works on a separate feature, fix, or documentation branch.
- Members can commit and push changes to their own working branches without prior approval.
- Direct pushes to protected `main` are not allowed.
- To propose changes for `main`, open a pull request and request **Ruthwar** as the reviewer.
- Ruthwar reviews the pull request, requests changes or approves it, and controls the final merge into `main`.
- Team members must not merge their own or another member's pull request into `main`.

## 1. Before you start

You need:

- Git installed on your computer.
- A GitHub account with **Write** access to the private repository.
- The repository invitation accepted.
- GitHub authentication configured on your computer. Use your own account; never share accounts or access tokens.

Repository URL:

```text
https://github.com/Ruthwar/bharatbiz-ai-capstone.git
```

If you are setting up Git for the first time, configure the name and email that will appear on your commits:

```bash
git config --global user.name "Your Name"
git config --global user.email "your-github-email@example.com"
```

## 2. Clone the repository once

Open Git Bash or PowerShell in the folder where you want to store the project, then run:

```bash
git clone https://github.com/Ruthwar/bharatbiz-ai-capstone.git
cd bharatbiz-ai-capstone
```

Cloning is a **one-time setup**. For later work, open the existing `bharatbiz-ai-capstone` folder and pull the latest changes instead of cloning again.

Check that you are connected to the correct repository:

```bash
git remote -v
```

The output should show the repository URL for both `fetch` and `push`.

## 3. Start each task with the latest code

Always update your local `main` branch before creating a working branch:

```bash
git checkout main
git pull origin main
```

Create a new branch with a short, descriptive name:

```bash
git checkout -b feature/short-description
```

Examples:

```bash
git checkout -b feature/inventory-validation
git checkout -b fix/supplier-date-parsing
git checkout -b docs/update-setup-guide
```

Use a separate branch for each task. Do not make unrelated changes in the same branch.

## 4. Make and review your changes

Edit the required files using your editor. Keep changes small and focused so they are easier to review and test.

See which files changed:

```bash
git status
```

Review the actual line-by-line changes:

```bash
git diff
```

Before continuing, confirm that:

- Only files related to your task changed.
- Your changes work as expected.
- No passwords, API keys, tokens, `.env` files, or identifiable pilot data are included.
- Generated environments and cache files such as `.venv/` and `__pycache__/` are not included.

## 5. Stage the changes

Stage each required file explicitly:

```bash
git add path/to/file1 path/to/file2
```

Examples:

```bash
git add app/agents/inventory.py
git add docs/GIT_COLLABORATION_GUIDE.md
```

Check what will be included in the commit:

```bash
git status
git diff --cached
```

If you staged a file by mistake but have not committed yet, unstage it without deleting your edits:

```bash
git restore --staged path/to/file
```

Avoid staging files blindly. Review the staged changes before every commit.

## 6. Commit the changes

Create a commit with a short message that describes the result:

```bash
git commit -m "Add inventory validation for missing stock"
```

Good commit messages are specific and use the imperative form, for example:

- `Add supplier delay edge case`
- `Fix order quantity parsing`
- `Update synthetic data documentation`

Avoid vague messages such as `changes`, `update`, or `final fix`.

A commit saves a snapshot in your **local** repository. It does not upload the changes to GitHub until you push.

## 7. Push your branch to GitHub

For the first push of your new branch:

```bash
git push -u origin feature/short-description
```

Replace `feature/short-description` with your actual branch name.

For later commits on the same branch:

```bash
git push
```

You do not need prior approval to push commits to your own working branch. Ruthwar reviews the changes when you submit the branch for merging into `main`.

Do not use `--force` or `--force-with-lease` unless the team has explicitly agreed why it is necessary. Never force-push `main`.

## 8. Open a pull request for Ruthwar's review

1. Open the repository on GitHub.
2. Select the option to create a **pull request** for your pushed branch.
3. Confirm that the base branch is `main` and the compare branch is your working branch.
4. Add a clear title and describe:
   - What changed.
   - Why it changed.
   - How you tested it.
   - Anything Ruthwar should check carefully.
5. Request **Ruthwar** as the reviewer.
6. Address review comments with new commits on the same branch.
7. Push again; the pull request updates automatically.
8. Wait for Ruthwar to approve and merge the pull request after the team's agreed checks pass.

Do not push directly to `main` and do not merge pull requests into `main`. GitHub may reject direct pushes because `main` is protected. Ruthwar controls the final merge.

## 9. Update your local repository after merging

After Ruthwar merges the pull request:

```bash
git checkout main
git pull origin main
```

If you no longer need the local working branch:

```bash
git branch -d feature/short-description
```

Start the next task by creating a fresh branch from the updated `main`.

## 10. If you encounter a problem

### Permission denied or repository not found

- Confirm that you accepted the repository invitation.
- Confirm that you signed in with the GitHub account that received access.
- Check the remote URL with `git remote -v`.
- Ask the repository owner to confirm that you have **Write** access.

### Your branch is behind the latest `main`

Before adding more work, commit or otherwise safeguard your current edits. Then ask the team or reviewer to help update your branch if you are unfamiliar with merging or rebasing. Do not discard changes or force-push just to make the warning disappear.

### Merge conflicts

A conflict means Git needs a person to choose how overlapping edits should fit together.

1. Read the conflict markers and both versions carefully.
2. Preserve the intended behavior of both changes where appropriate.
3. Remove all conflict markers.
4. Test the result before committing.
5. Ask the other author or your reviewer for help if the correct result is unclear.

### You made a mistake

Stop before deleting files, resetting branches, or force-pushing. Share the output of these commands with a team lead or reviewer:

```bash
git status
git branch --show-current
git log --oneline -5
```

## Quick-reference workflow

```bash
# Start from the latest main
git checkout main
git pull origin main
git checkout -b feature/short-description

# After editing and testing
git status
git diff
git add path/to/changed-file
git diff --cached
git commit -m "Describe the change clearly"

# Upload the branch without waiting for prior approval
git push -u origin feature/short-description

# Open a pull request on GitHub and request Ruthwar as the reviewer
# Wait for Ruthwar to approve and merge it into protected main

# After Ruthwar merges the pull request
git checkout main
git pull origin main
```

## Team checklist for every contribution

- [ ] I started from the latest `main`.
- [ ] I created a separate, clearly named branch.
- [ ] My changes are small and focused on one task.
- [ ] I reviewed `git status`, `git diff`, and the staged diff.
- [ ] I tested the changes.
- [ ] I included no secrets or unauthorized/identifiable data.
- [ ] I wrote a clear commit message.
- [ ] I pushed my working branch without pushing directly to `main`.
- [ ] I opened a pull request and requested Ruthwar as the reviewer.
- [ ] I completed the agreed checks and addressed Ruthwar's review comments.
- [ ] I left the final approval and merge into `main` to Ruthwar.
