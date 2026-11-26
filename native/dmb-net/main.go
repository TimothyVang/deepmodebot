package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"encoding/xml"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"sort"
	"strings"
	"sync"
	"syscall"
	"time"
)

const version = "0.1.0"

func main() {
	if len(os.Args) < 2 {
		printHelp()
		os.Exit(0)
	}
	sub := os.Args[1]
	rest := os.Args[2:]
	var err error
	switch sub {
	case "-h", "--help", "help":
		printHelp()
	case "-V", "--version":
		fmt.Println("dmb-net", version)
	case "trending":
		err = runTrending(rest)
	case "pr-overlap":
		err = runPROverlap(rest)
	case "fetch-papers":
		err = runFetchPapers(rest)
	case "webhook":
		err = runWebhook(rest)
	default:
		fmt.Fprintf(os.Stderr, "dmb-net: unknown subcommand %q\n", sub)
		printHelp()
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "dmb-net %s: %v\n", sub, err)
		os.Exit(1)
	}
}

func printHelp() {
	fmt.Println(`dmb-net ` + version + ` — zero-dependency concurrent Go network/API engine for deepmodebot
Usage:
  dmb-net trending [--topics rust,go,deep-learning] [--limit 10] [--json]
  dmb-net pr-overlap [--repo owner/name] [--json]
  dmb-net fetch-papers [--ids 2106.06981,2301.05062] [--query "reinforcement learning"] [--limit 10] [--json]
  dmb-net webhook [--addr 127.0.0.1:8787] [--secret-env DMB_WEBHOOK_SECRET]`)
}

// -----------------------------------------------------------------------------
// 1. Concurrent GitHub Trending Fetcher (replaces scripts/trending.py)
// -----------------------------------------------------------------------------

type RepoItem struct {
	FullName    string `json:"full_name"`
	Stars       int    `json:"stargazers_count"`
	Language    string `json:"language"`
	Description string `json:"description"`
	HTMLURL     string `json:"html_url"`
	Topic       string `json:"topic,omitempty"`
}

type ghSearchResp struct {
	Items []RepoItem `json:"items"`
}

func fetchTopicRepos(ctx context.Context, client *http.Client, baseURL, topic string, limit int) ([]RepoItem, error) {
	q := url.QueryEscape("topic:" + topic + " stars:>100")
	reqURL := fmt.Sprintf("%s/search/repositories?q=%s&sort=stars&order=desc&per_page=%d", strings.TrimRight(baseURL, "/"), q, limit)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("User-Agent", "deepmodebot-dmb-net/"+version)
	if tok := os.Getenv("GITHUB_TOKEN"); tok != "" {
		req.Header.Set("Authorization", "Bearer "+tok)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("github status %d for topic %s", resp.StatusCode, topic)
	}
	var parsed ghSearchResp
	if err := json.NewDecoder(io.LimitReader(resp.Body, 4<<20)).Decode(&parsed); err != nil {
		return nil, err
	}
	for i := range parsed.Items {
		parsed.Items[i].Topic = topic
	}
	return parsed.Items, nil
}

func runTrending(args []string) error {
	fs := flag.NewFlagSet("trending", flag.ContinueOnError)
	topicsFlag := fs.String("topics", "deep-learning,reinforcement-learning,rust", "comma-separated GitHub topics")
	limit := fs.Int("limit", 5, "repos per topic")
	asJSON := fs.Bool("json", false, "output JSON")
	apiBase := fs.String("api-base", "https://api.github.com", "GitHub API base URL")
	if err := fs.Parse(args); err != nil {
		return err
	}
	topics := splitCSV(*topicsFlag)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()

	client := &http.Client{Timeout: 15 * time.Second}
	var (
		mu      sync.Mutex
		wg      sync.WaitGroup
		all     []RepoItem
		errs    []string
		sem     = make(chan struct{}, 4)
		seen    = make(map[string]bool)
	)
	for _, t := range topics {
		wg.Add(1)
		go func(topic string) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			items, err := fetchTopicRepos(ctx, client, *apiBase, topic, *limit)
			mu.Lock()
			defer mu.Unlock()
			if err != nil {
				errs = append(errs, err.Error())
				return
			}
			for _, it := range items {
				if !seen[it.FullName] {
					seen[it.FullName] = true
					all = append(all, it)
				}
			}
		}(t)
	}
	wg.Wait()
	sort.Slice(all, func(i, j int) bool { return all[i].Stars > all[j].Stars })

	if *asJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(map[string]any{
			"engine": "go-goroutines",
			"count":  len(all),
			"errors": errs,
			"repos":  all,
		})
	}
	fmt.Printf("dmb-net trending: %d repo(s) across %d topic(s)\n", len(all), len(topics))
	for _, r := range all {
		fmt.Printf("  %6d* | %-12s | %s — %s\n", r.Stars, r.Language, r.FullName, truncate(r.Description, 68))
	}
	return nil
}

// -----------------------------------------------------------------------------
// 2. Concurrent PR File-Overlap Collision Detector (replaces pr-overlap.py)
// -----------------------------------------------------------------------------

type PRFiles struct {
	Number int      `json:"number"`
	Title  string   `json:"title"`
	Author string   `json:"author"`
	Files  []string `json:"files"`
}

type Overlap struct {
	PRA   int      `json:"pr_a"`
	PRB   int      `json:"pr_b"`
	Files []string `json:"files"`
}

func computeOverlaps(prs []PRFiles) []Overlap {
	var overlaps []Overlap
	for i := range prs {
		setA := make(map[string]struct{}, len(prs[i].Files))
		for _, f := range prs[i].Files {
			setA[f] = struct{}{}
		}
		for j := i + 1; j < len(prs); j++ {
			var shared []string
			for _, f := range prs[j].Files {
				if _, ok := setA[f]; ok {
					shared = append(shared, f)
				}
			}
			if len(shared) > 0 {
				sort.Strings(shared)
				overlaps = append(overlaps, Overlap{PRA: prs[i].Number, PRB: prs[j].Number, Files: shared})
			}
		}
	}
	sort.Slice(overlaps, func(i, j int) bool {
		if overlaps[i].PRA != overlaps[j].PRA {
			return overlaps[i].PRA < overlaps[j].PRA
		}
		return overlaps[i].PRB < overlaps[j].PRB
	})
	return overlaps
}

func runPROverlap(args []string) error {
	fs := flag.NewFlagSet("pr-overlap", flag.ContinueOnError)
	repo := fs.String("repo", "", "owner/repo (default: infer from gh)")
	asJSON := fs.Bool("json", false, "output JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
	defer cancel()

	ghArgs := []string{"pr", "list", "--state", "open", "--limit", "50", "--json", "number,title,author,files"}
	if *repo != "" {
		ghArgs = append(ghArgs, "--repo", *repo)
	}
	cmd := exec.CommandContext(ctx, "gh", ghArgs...)
	out, err := cmd.Output()
	if err != nil {
		return fmt.Errorf("gh pr list failed: %w", err)
	}
	var raw []struct {
		Number int    `json:"number"`
		Title  string `json:"title"`
		Author struct {
			Login string `json:"login"`
		} `json:"author"`
		Files []struct {
			Path string `json:"path"`
		} `json:"files"`
	}
	if err := json.Unmarshal(out, &raw); err != nil {
		return err
	}
	prs := make([]PRFiles, len(raw))
	for i, r := range raw {
		files := make([]string, len(r.Files))
		for k, f := range r.Files {
			files[k] = f.Path
		}
		prs[i] = PRFiles{Number: r.Number, Title: r.Title, Author: r.Author.Login, Files: files}
	}
	overlaps := computeOverlaps(prs)
	if *asJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(map[string]any{
			"engine":   "go-goroutines",
			"open_prs": len(prs),
			"overlaps": overlaps,
		})
	}
	fmt.Printf("dmb-net pr-overlap: %d open PR(s), %d overlap pair(s)\n", len(prs), len(overlaps))
	for _, ov := range overlaps {
		fmt.Printf("  PR #%d <-> PR #%d: %s\n", ov.PRA, ov.PRB, strings.Join(ov.Files, ", "))
	}
	return nil
}

// -----------------------------------------------------------------------------
// 3. Concurrent arXiv Research Paper Scraper (for deep-learning / research)
// -----------------------------------------------------------------------------

type arxivFeed struct {
	Entries []arxivEntry `xml:"entry"`
}

type arxivEntry struct {
	ID        string        `xml:"id"`
	Title     string        `xml:"title"`
	Published string        `xml:"published"`
	Summary   string        `xml:"summary"`
	Authors   []arxivAuthor `xml:"author"`
}

type arxivAuthor struct {
	Name string `xml:"name"`
}

type Paper struct {
	ID      string   `json:"id"`
	Date    string   `json:"date"`
	Title   string   `json:"title"`
	Authors []string `json:"authors"`
	Summary string   `json:"summary"`
}

func parseArxivXML(r io.Reader) ([]Paper, error) {
	var feed arxivFeed
	if err := xml.NewDecoder(io.LimitReader(r, 8<<20)).Decode(&feed); err != nil {
		return nil, err
	}
	papers := make([]Paper, 0, len(feed.Entries))
	for _, e := range feed.Entries {
		id := e.ID
		if idx := strings.LastIndex(id, "/"); idx >= 0 {
			id = id[idx+1:]
		}
		if idx := strings.Index(id, "v"); idx > 0 {
			id = id[:idx]
		}
		date := e.Published
		if len(date) >= 10 {
			date = date[:10]
		}
		authors := make([]string, 0, len(e.Authors))
		for _, a := range e.Authors {
			if len(authors) < 3 {
				authors = append(authors, strings.TrimSpace(a.Name))
			}
		}
		papers = append(papers, Paper{
			ID:      id,
			Date:    date,
			Title:   collapseSpaces(e.Title),
			Authors: authors,
			Summary: truncate(collapseSpaces(e.Summary), 220),
		})
	}
	return papers, nil
}

func runFetchPapers(args []string) error {
	fs := flag.NewFlagSet("fetch-papers", flag.ContinueOnError)
	ids := fs.String("ids", "", "comma-separated arXiv IDs")
	query := fs.String("query", "", "arXiv search query (e.g. 'cat:cs.LG AND reinforcement learning')")
	limit := fs.Int("limit", 10, "max results")
	asJSON := fs.Bool("json", false, "output JSON")
	apiBase := fs.String("api-base", "https://export.arxiv.org/api/query", "arXiv API endpoint")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *ids == "" && *query == "" {
		return errors.New("provide --ids or --query")
	}
	params := url.Values{}
	if *ids != "" {
		params.Set("id_list", *ids)
	}
	if *query != "" {
		params.Set("search_query", *query)
	}
	params.Set("max_results", fmt.Sprintf("%d", *limit))

	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, *apiBase+"?"+params.Encode(), nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", "deepmodebot-dmb-net/"+version)
	client := &http.Client{Timeout: 18 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("arxiv status %d", resp.StatusCode)
	}
	papers, err := parseArxivXML(resp.Body)
	if err != nil {
		return err
	}
	if *asJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(map[string]any{
			"engine": "go-http",
			"count":  len(papers),
			"papers": papers,
		})
	}
	fmt.Printf("dmb-net fetch-papers: %d paper(s)\n", len(papers))
	for _, p := range papers {
		fmt.Printf("  [%s] (%s) %s — %s\n", p.ID, p.Date, p.Title, strings.Join(p.Authors, ", "))
	}
	return nil
}

// -----------------------------------------------------------------------------
// 4. Low-RAM Concurrent GitHub Webhook Receiver (HMAC-SHA256 verified)
// -----------------------------------------------------------------------------

func verifyGitHubSignature(secret, sigHeader string, body []byte) bool {
	if secret == "" || !strings.HasPrefix(sigHeader, "sha256=") {
		return false
	}
	gotHex := strings.TrimPrefix(sigHeader, "sha256=")
	got, err := hex.DecodeString(gotHex)
	if err != nil {
		return false
	}
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	expected := mac.Sum(nil)
	return hmac.Equal(got, expected)
}

func newWebhookHandler(secret string, onEvent func(event string, body []byte)) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true,"engine":"go-net"}`))
	})
	mux.HandleFunc("/webhook", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		body, err := io.ReadAll(io.LimitReader(r.Body, (1<<20)+1))
		if err != nil {
			http.Error(w, "read failed", http.StatusBadRequest)
			return
		}
		if len(body) > 1<<20 {
			http.Error(w, "payload too large", http.StatusRequestEntityTooLarge)
			return
		}
		if !verifyGitHubSignature(secret, r.Header.Get("X-Hub-Signature-256"), body) {
			http.Error(w, "invalid signature", http.StatusUnauthorized)
			return
		}
		ev := r.Header.Get("X-GitHub-Event")
		if onEvent != nil {
			go onEvent(ev, body)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"accepted":true}`))
	})
	return mux
}

func runWebhook(args []string) error {
	fs := flag.NewFlagSet("webhook", flag.ContinueOnError)
	addr := fs.String("addr", "127.0.0.1:8787", "listen address")
	secretEnv := fs.String("secret-env", "DMB_WEBHOOK_SECRET", "env var holding GitHub webhook secret")
	if err := fs.Parse(args); err != nil {
		return err
	}
	secret := os.Getenv(*secretEnv)
	if secret == "" {
		return fmt.Errorf("missing webhook secret in env %s (fail-closed)", *secretEnv)
	}
	srv := &http.Server{
		Addr:              *addr,
		Handler:           newWebhookHandler(secret, func(ev string, body []byte) { fmt.Printf("event=%s bytes=%d\n", ev, len(body)) }),
		ReadHeaderTimeout: 5 * time.Second,
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutCtx)
	}()
	fmt.Printf("dmb-net webhook listening on %s\n", *addr)
	err := srv.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}

func splitCSV(s string) []string {
	var out []string
	for _, part := range strings.Split(s, ",") {
		if t := strings.TrimSpace(part); t != "" {
			out = append(out, t)
		}
	}
	return out
}

func collapseSpaces(s string) string {
	return strings.Join(strings.Fields(s), " ")
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "..."
}
