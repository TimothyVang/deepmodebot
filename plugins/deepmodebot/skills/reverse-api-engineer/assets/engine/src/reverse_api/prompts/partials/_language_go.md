**Generate a Go program** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Prefer the standard library (`net/http`, `encoding/json`) — a single-file program with no external dependencies is the default; only introduce a module and third-party packages if the API genuinely needs something the standard library doesn't provide (e.g. a specific auth scheme's signing library)
- Reuse one `*http.Client` (with cookie jar if the API relies on cookies) across requests rather than creating a new one per call
- Create a separate function for each distinct API endpoint, with a typed struct for its response shape
- Return errors rather than panicking; wrap them with context (`fmt.Errorf("...: %w", err)`)
- Include a `main` function with example usage

**Authentication & credentials:**
- Read required credentials from caller-supplied environment variables; fail clearly when absent.
- Never embed captured cookies, tokens, session IDs, or authentication headers in source or logs.
- Do not log in, recover credentials, or automatically refresh authentication on 401/403.

**Testing:**
- If a module was initialized, first run: `go mod tidy`
- Format the code with: `gofmt -w {client_filename}`
- Run with: `{run_command}`
- You have up to 5 attempts to fix issues

Save the program to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
If external dependencies are used, save the module files: `{scripts_dir}/go.mod` and `{scripts_dir}/go.sum`
