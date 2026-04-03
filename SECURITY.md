# Security Policy

## Supported Versions

Security fixes are prioritized for:

| Version | Supported |
|---|---|
| main (latest commit) | Yes |
| Latest tagged release | Yes |
| Older releases | Best effort |

## Reporting a Vulnerability

Please do not report security vulnerabilities in public issues.

Use one of the following private channels:

1. GitHub Security Advisory (preferred):
   - Open a private vulnerability report in the repository Security tab.
2. If Security Advisory is unavailable, contact maintainers privately through GitHub.

## What to Include in a Report

Please include as much detail as possible:

- Affected component and file paths
- Impact assessment (confidentiality, integrity, availability)
- Reproduction steps or proof of concept
- Version, commit hash, and environment details
- Suggested mitigation if available

High-quality reports help us validate and fix issues faster.

## Response Process

Our typical process is:

1. Acknowledge report within 3 business days.
2. Triage and severity assessment within 7 business days when possible.
3. Work on fix and coordinate disclosure timeline with reporter.
4. Publish advisory and remediation guidance after fix is available.

Response times can vary based on complexity and maintainer availability.

## Coordinated Disclosure

We follow coordinated disclosure principles:

- Keep details private until users can apply a fix.
- Credit reporters when they request attribution.
- Publish clear remediation instructions after release.

## Security Best Practices for Contributors

When submitting code:

- Avoid committing secrets, credentials, or tokens.
- Validate all untrusted inputs.
- Use safe defaults and least privilege.
- Keep dependencies updated and pinned when practical.
- Add tests for security-relevant behavior.

## Scope Notes

Out-of-scope reports generally include:

- Issues requiring unrealistic attacker assumptions
- Social engineering without a technical vulnerability
- Denial of service from extreme, non-practical resource scenarios

If you are unsure whether something is in scope, report it privately and we will help triage.

## Thanks

We appreciate responsible disclosure and the time spent helping improve OpenSynaptic security.
