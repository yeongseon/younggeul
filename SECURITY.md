# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Email: security@younggeul.dev (or use GitHub's private vulnerability reporting)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
4. We will acknowledge within 48 hours and provide a timeline for a fix

## Security Considerations

- API keys (DATA_GO_KR_API_KEY, LITELLM_API_KEY) must never be committed to the repository
- Public PRs from forks do not have access to repository secrets
- Self-hosted runners are not used for public PRs (to prevent secret exfiltration)
