package main

import (
	"fmt"
	"io"
	"net"
	"net/http"
	"net/netip"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestFailureDescriptionsDoNotExposeDNSAnswers(t *testing.T) {
	cases := []struct {
		cause             error
		kind, description string
	}{
		{fmt.Errorf("%w: %w", errDNS, &net.DNSError{IsNotFound: true}), "dns", "dns_not_found"},
		{fmt.Errorf("%w: %w", errDNS, &net.DNSError{IsTemporary: true}), "dns", "dns_temporary"},
		{fmt.Errorf("%w: %w", errDNS, &net.DNSError{IsTimeout: true}), "dns", "dns_timeout"},
		{fmt.Errorf("%w: %w", errDNS, syscall.EMFILE), "network", "local_file_limit"},
	}
	for _, item := range cases {
		client := nativeClient()
		client.Transport = fixtureTransport(func(r *http.Request) (*http.Response, error) {
			return nil, item.cause
		})
		result := probe(client, request{URL: "https://example.org/alice"})
		if result.ErrorKind != item.kind || result.Error != item.description {
			t.Fatalf("unexpected failure: %+v", result)
		}
	}
}

type fixtureTransport func(*http.Request) (*http.Response, error)

func (f fixtureTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestPublicTargets(t *testing.T) {
	for _, value := range []string{"127.0.0.1", "10.0.0.1", "::1", "169.254.1.1", "100.64.1.1", "192.0.2.1", "2001:db8::1", "::ffff:192.168.1.1"} {
		if publicAddress(netip.MustParseAddr(value)) {
			t.Fatal("private target allowed", value)
		}
	}
	if !publicAddress(netip.MustParseAddr("1.1.1.1")) {
		t.Fatal("public target rejected")
	}
}

func TestProbeDoesNotFollowRedirectsOrRetainCookies(t *testing.T) {
	count := 0
	client := nativeClient()
	client.Transport = fixtureTransport(func(r *http.Request) (*http.Response, error) {
		count++
		if r.Method != "GET" || r.Header.Get("Cookie") != "" {
			t.Fatal("unexpected credentials or method")
		}
		return &http.Response{StatusCode: 302, Header: http.Header{"Location": {"https://example.org/login"}, "Set-Cookie": {"session=secret"}}, Body: io.NopCloser(strings.NewReader("redirect")), Request: r}, nil
	})
	out := probe(client, request{ID: 7, URL: "https://example.org/demo", UserAgent: "idlink/test"})
	if count != 1 || out.Status != 302 || out.ID != 7 || out.Headers["Set-Cookie"] != "" {
		t.Fatal("redirect or cookie handling failed")
	}
}

func TestUnsafeURLNeverCallsTransport(t *testing.T) {
	client := nativeClient()
	client.Transport = fixtureTransport(func(r *http.Request) (*http.Response, error) { t.Fatal("unexpected request"); return nil, nil })
	for _, value := range []string{"http://example.org", "https://user:pass@example.org", "https://example.org:8080"} {
		if probe(client, request{URL: value}).Error == "" {
			t.Fatal("unsafe URL accepted")
		}
	}
}

func TestDeadlineCancelsUnresponsiveRequest(t *testing.T) {
	client := nativeClient()
	client.Transport = fixtureTransport(func(r *http.Request) (*http.Response, error) {
		<-r.Context().Done()
		return nil, r.Context().Err()
	})
	start := time.Now()
	output := probe(client, request{URL: "https://example.org/alice", TimeoutMS: 10})
	if output.ErrorKind != "timeout" || output.Error == "" || time.Since(start) > 500*time.Millisecond {
		t.Fatal("deadline not enforced")
	}
}

func TestInvalidDeadlineNeverCallsTransport(t *testing.T) {
	client := nativeClient()
	client.Transport = fixtureTransport(func(r *http.Request) (*http.Response, error) { t.Fatal("unexpected request"); return nil, nil })
	for _, timeout := range []int{-1, 120001} {
		if probe(client, request{URL: "https://example.org/alice", TimeoutMS: timeout}).Error == "" {
			t.Fatal("invalid deadline accepted")
		}
	}
}
