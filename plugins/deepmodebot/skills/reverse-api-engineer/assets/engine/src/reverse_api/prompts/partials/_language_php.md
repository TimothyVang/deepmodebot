**Generate a PHP script** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Use the `curl` extension (`curl_init`/`curl_exec`) for requests and `json_encode`/`json_decode` for JSON. No Composer dependency is needed. If `curl_init` is unavailable, report that the PHP curl extension is required and stop; do not install system packages.
- Reuse one cURL handle across requests rather than creating a new one per call
- Create a separate function for each distinct API endpoint
- Include type declarations on function signatures where they add clarity
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
