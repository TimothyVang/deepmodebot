**Generate a JavaScript module** that replicates the API calls found in the traffic. The following are guidelines — use your judgment:

- Use modern JavaScript (ES2022+) with ESM modules
- Prefer native `fetch` (Node.js 18+); use `axios` only if you need retries or interceptors
- Create separate async functions for each endpoint
- Add JSDoc comments and error handling where they add clarity
- Include example usage in a main section
- If using external deps, generate a `package.json` with `"type": "module"`

**Authentication & credentials:**
- Read required credentials from caller-supplied environment variables; fail clearly when absent.
- Never embed captured cookies, tokens, session IDs, or authentication headers in source or logs.
- Do not log in, recover credentials, or automatically refresh authentication on 401/403.

**Testing:**
- If `package.json` was generated, first run: `npm install`
- Run with: `{run_command}`
- You have up to 5 attempts to fix issues

Save the module to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
If external dependencies are used, save: `{scripts_dir}/package.json`