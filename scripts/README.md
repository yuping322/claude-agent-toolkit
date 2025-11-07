# Auto PR from Issues

This GitHub Action automatically analyzes GitHub issues and creates pull requests with fixes using the Claude Agent Toolkit.

## How it works

When an issue is created with the `auto-fix` label or containing `auto-fix` in the body, the action will:

1. **Analyze the codebase** - Understand the project structure and patterns
2. **Analyze the issue** - Understand what needs to be fixed
3. **Generate a fix** - Use Claude to create appropriate code changes
4. **Implement changes** - Modify the relevant files
5. **Create a PR** - Push changes to a new branch and create a pull request

## Setup

### 1. Required Secrets

Add these secrets to your GitHub repository:

- `CLAUDE_CODE_OAUTH_TOKEN`: Your Claude Code OAuth token (get from [Claude Code](https://claude.ai/code))

#### How to get CLAUDE_CODE_OAUTH_TOKEN:

1. **Visit Claude Code**: Go to [https://claude.ai/code](https://claude.ai/code)
2. **Login**: Sign in with your Anthropic account
3. **Get Token**: Run the command `claude setup-token` in your terminal, or find the token in the Claude Code interface
4. **Copy Token**: Copy the generated OAuth token

#### How to configure in GitHub:

1. **Go to Repository Settings**:
   - Open your GitHub repository
   - Click on "Settings" tab
   - Scroll down and click on "Secrets and variables" → "Actions"

2. **Add New Secret**:
   - Click "New repository secret"
   - Name: `CLAUDE_CODE_OAUTH_TOKEN`
   - Value: Paste your Claude Code OAuth token
   - Click "Add secret"

The `GITHUB_TOKEN` is automatically provided by GitHub Actions.

### 2. Workflow File

The workflow file is already created at `.github/workflows/auto-pr.yml`.

### 3. Trigger the Action

To trigger the auto-fix action, create an issue with:

- **Label**: Add the `auto-fix` label, OR
- **Body**: Include `auto-fix` anywhere in the issue description

## Example Usage

Create an issue like this:

```
Title: Fix typo in README.md

Body:
auto-fix

There's a typo on line 15 of the README.md file. It says "teh" instead of "the".
```

The action will automatically:
1. Analyze the README.md file
2. Find the typo
3. Fix it
4. Create a PR with the fix

## Supported Issue Types

The system can handle various types of issues:

- **Bug fixes** - Logic errors, typos, incorrect calculations
- **Documentation** - Missing or incorrect documentation
- **Code improvements** - Better error handling, performance optimizations
- **Feature additions** - Small feature implementations

## Limitations

- Currently works best with clear, specific issues
- Complex architectural changes may require manual review
- Large-scale refactoring is not recommended
- Requires Claude Code access

## Customization

You can modify the behavior by editing the `scripts/auto_fix_issue.py` file:

- Change the AI model (currently uses "sonnet")
- Modify the analysis prompts
- Add custom tools for specific project needs
- Adjust the PR creation logic

## Troubleshooting

### Action doesn't trigger
- Ensure the issue has the `auto-fix` label OR contains `auto-fix` in the body
- Check that the workflow file is in `.github/workflows/auto-pr.yml`

### Claude API errors
- Verify your `CLAUDE_CODE_OAUTH_TOKEN` is valid and has access to Claude Code
- Check the action logs for specific error messages

### Git operations fail
- Ensure the repository has proper permissions for the GITHUB_TOKEN
- Check that the default branch is "main" (or update the script accordingly)

## Security Considerations

- The action only runs on issues with explicit `auto-fix` triggers
- All changes are made in separate branches
- PRs require manual review before merging
- The action cannot access secrets or private repositories beyond the current one