package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestComputeOverlaps(t *testing.T) {
	prs := []PRFiles{
		{Number: 10, Files: []string{"src/a.rs", "src/b.rs"}},
		{Number: 12, Files: []string{"src/b.rs", "src/c.rs"}},
		{Number: 15, Files: []string{"docs/readme.md"}},
	}
	ov := computeOverlaps(prs)
	if len(ov) != 1 || ov[0].PRA != 10 || ov[0].PRB != 12 || len(ov[0].Files) != 1 || ov[0].Files[0] != "src/b.rs" {
		t.Fatalf("unexpected overlaps: %+v", ov)
	}
}

func TestParseArxivXML(t *testing.T) {
	sample := `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.05062v2</id>
    <published>2023-01-12T18:00:00Z</published>
    <title>Tracr: Compiled Transformers</title>
    <summary>Compiles RASP programs into weights.</summary>
    <author><name>David Lindner</name></author>
  </entry>
</feed>`
	papers, err := parseArxivXML(strings.NewReader(sample))
	if err != nil {
		t.Fatalf("parseArxivXML error: %v", err)
	}
	if len(papers) != 1 || papers[0].ID != "2301.05062" || papers[0].Date != "2023-01-12" {
		t.Fatalf("unexpected paper: %+v", papers)
	}
}

func TestWebhookHMACVerification(t *testing.T) {
	secret := "test-webhook-secret"
	body := []byte(`{"action":"opened"}`)
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	validSig := "sha256=" + hex.EncodeToString(mac.Sum(nil))

	done := make(chan string, 1)
	srv := httptest.NewServer(newWebhookHandler(secret, func(ev string, _ []byte) { done <- ev }))
	defer srv.Close()

	// 1. Invalid signature rejected (fail-closed)
	reqBad, _ := http.NewRequest(http.MethodPost, srv.URL+"/webhook", bytes.NewReader(body))
	reqBad.Header.Set("X-Hub-Signature-256", "sha256=deadbeef")
	respBad, err := http.DefaultClient.Do(reqBad)
	if err != nil {
		t.Fatal(err)
	}
	respBad.Body.Close()
	if respBad.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 for bad sig, got %d", respBad.StatusCode)
	}

	// 2. Valid signature accepted & dispatched concurrently
	reqOk, _ := http.NewRequest(http.MethodPost, srv.URL+"/webhook", bytes.NewReader(body))
	reqOk.Header.Set("X-Hub-Signature-256", validSig)
	reqOk.Header.Set("X-GitHub-Event", "pull_request")
	respOk, err := http.DefaultClient.Do(reqOk)
	if err != nil {
		t.Fatal(err)
	}
	respOk.Body.Close()
	if respOk.StatusCode != http.StatusAccepted {
		t.Fatalf("expected 202 for valid sig, got %d", respOk.StatusCode)
	}
	if got := <-done; got != "pull_request" {
		t.Fatalf("expected event pull_request, got %q", got)
	}
}

func TestFetchTopicReposMockServer(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"items":[{"full_name":"a/b","stargazers_count":500,"language":"Rust","description":"fast"}]}`))
	}))
	defer srv.Close()
	items, err := fetchTopicRepos(context.Background(), srv.Client(), srv.URL, "rust", 5)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].FullName != "a/b" || items[0].Topic != "rust" {
		t.Fatalf("unexpected items: %+v", items)
	}
}
