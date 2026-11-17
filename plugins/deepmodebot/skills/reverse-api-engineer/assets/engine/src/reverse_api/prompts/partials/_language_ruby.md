**Generate a Ruby script** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Use `net/http` and `json` for requests and JSON — both are part of Ruby's standard library, so no gem/Bundler dependency is needed
- Reuse persistent connections (`Net::HTTP.start` held open across calls) rather than opening a new connection per request — use a separate connection per distinct scheme/host/port, since one is bound to a single origin and captured traffic may span several (e.g. separate login, API, and upload hosts)
- Create a separate method for each distinct API endpoint
- Include example usage at the bottom of the script

**Authentication & credentials:**
- Read required credentials from caller-supplied environment variables; fail clearly when absent.
- Never embed captured cookies, tokens, session IDs, or authentication headers in source or logs.
- Do not log in, recover credentials, or automatically refresh authentication on 401/403.

**Testing:**
- Run: `{run_command}`
- You have up to 5 attempts to fix issues

Save the script to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
