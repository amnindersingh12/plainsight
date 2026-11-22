# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub:
**[Report a vulnerability](https://github.com/amnindersingh12/plainsight/security/advisories/new)**
(Security tab, "Report a vulnerability"). Do not open a public issue for them.

Include the tool and version, the input or command that triggers the problem, and what an attacker gains.
You should get a first reply within 7 days.

## What counts

- **unseen**: any input that hides a tag-character, bidi or zero-width payload from a default scan (a false
  negative), or that makes the GitHub Action or pre-commit hook skip files it should scan. Command injection
  through file names or pull request data in `unseen/action.yml`.
- **stegsweep**: anything an untrusted input file can do beyond being analysed: writing outside the report
  directory, HTML or terminal escape injection, executing extracted data, or unbounded memory, disk or CPU use
  beyond the documented limits.
- **stegsurvive**: `reveal` returning a wrong message instead of failing, a password mode that is weaker than
  documented, or crashes on crafted images.

Known, documented limits (for example that stegsurvive's built-in password mode is obfuscation-grade without
the `[crypto]` extra, or that stegsurvive output is not hidden from steganalysis) are not vulnerabilities.

## Supported versions

Only the latest release of each package receives fixes.
