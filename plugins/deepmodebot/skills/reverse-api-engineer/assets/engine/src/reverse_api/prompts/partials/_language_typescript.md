**Generate a TypeScript module** that replicates the API calls found in the traffic. The following are guidelines — use your judgment:

- Use strict typing with interfaces for request/response types
- Use ESM modules and native `fetch` (Node.js 18+); use `axios` only if needed
- Create separate async functions for each endpoint
- Export a class-based API client with proper encapsulation
- Include example usage in a main section
- Generate a `package.json` with `"type": "module"`, `tsx`, `typescript`, `@types/node`

**Authentication & credentials:**
- Read required credentials from caller-supplied environment variables; fail clearly when absent.
- Never embed captured cookies, tokens, session IDs, or authentication headers in source or logs.
- Do not log in, recover credentials, or automatically refresh authentication on 401/403.

**Testing:**
- Run: `npm install && {run_command}`
- You have up to 5 attempts to fix issues

Save the module to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
Save the package.json to: `{scripts_dir}/package.json`