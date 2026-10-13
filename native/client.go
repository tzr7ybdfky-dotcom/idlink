// Package main provides the optional GET-only native transport for idlink.
package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"strings"
	"syscall"
	"time"
)

// Private and reserved targets are never reachable through the native transport.
var errDNS = errors.New("DNS unavailable")
var errTarget = errors.New("non-public network target")

var forbidden = []string{
	"0.0.0.0/8", "100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15",
	"198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4", "2001::/23", "2001:db8::/32", "2002::/16", "64:ff9b:1::/48", "fec0::/10",
}

func publicAddress(value netip.Addr) bool {
	value = value.Unmap()
	if !value.IsGlobalUnicast() || value.IsPrivate() || value.IsLoopback() || value.IsLinkLocalUnicast() {
		return false
	}
	for _, block := range forbidden {
		if netip.MustParsePrefix(block).Contains(value) {
			return false
		}
	}
	return true
}

// resolveAndDial pins an approved DNS answer, avoiding a second DNS lookup.
func resolveAndDial(ctx context.Context, network, address string) (net.Conn, error) {
	host, port, err := net.SplitHostPort(address)
	if err != nil || port != "443" {
		return nil, errors.New("invalid network target")
	}
	answers, err := net.DefaultResolver.LookupNetIP(ctx, "ip", host)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", errDNS, err)
	}
	if len(answers) == 0 {
		return nil, errDNS
	}
	for _, answer := range answers {
		if !publicAddress(answer) {
			return nil, errTarget
		}
	}
	var dialer net.Dialer
	var lastError error
	for _, answer := range answers {
		attempt, cancel := context.WithTimeout(ctx, 1500*time.Millisecond)
		connection, e := dialer.DialContext(attempt, network, net.JoinHostPort(answer.String(), port))
		cancel()
		if e == nil {
			return connection, nil
		}
		lastError = e
	}
	return nil, fmt.Errorf("connection failed: %w", lastError)
}

func nativeClient() *http.Client {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	transport.DialContext = resolveAndDial
	transport.MaxIdleConns = 256
	transport.MaxIdleConnsPerHost = 4
	return &http.Client{
		Transport: transport, Timeout: 120 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error { return http.ErrUseLastResponse },
	}
}

// probe makes one request; robots and per-host rate policies remain in Python.
func probe(client *http.Client, input request) response {
	output := response{ID: input.ID}
	target, err := url.Parse(input.URL)
	if err != nil || target.Scheme != "https" || target.Hostname() == "" || target.User != nil ||
		(target.Port() != "" && target.Port() != "443") || strings.ContainsAny(input.UserAgent, "\r\n") {
		output.Error, output.ErrorKind = "invalid request", "policy"
		return output
	}
	timeout := input.TimeoutMS
	if timeout == 0 {
		timeout = 6000
	}
	if timeout < 1 || timeout > 120000 {
		output.Error, output.ErrorKind = "invalid timeout", "policy"
		return output
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Millisecond)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, "GET", input.URL, nil)
	if err != nil {
		output.Error, output.ErrorKind = "invalid request", "policy"
		return output
	}
	req.Header.Set("User-Agent", input.UserAgent)
	req.Header.Set("Cookie", "")
	result, err := client.Do(req)
	if err != nil {
		output.Error, output.ErrorKind = "request failed", "network"
		var dnsFailure *net.DNSError
		switch {
		case ctx.Err() != nil || errors.Is(err, context.DeadlineExceeded):
			output.ErrorKind = "timeout"
		case errors.Is(err, syscall.EMFILE) || errors.Is(err, syscall.ENFILE):
			output.Error = "local_file_limit"
		case errors.Is(err, errDNS):
			output.ErrorKind = "dns"
			if errors.As(err, &dnsFailure) {
				switch {
				case dnsFailure.IsNotFound:
					output.Error = "dns_not_found"
				case dnsFailure.IsTimeout:
					output.Error = "dns_timeout"
				case dnsFailure.IsTemporary:
					output.Error = "dns_temporary"
				}
			}
		case errors.Is(err, errTarget):
			output.ErrorKind = "policy"
		}
		return output
	}
	defer result.Body.Close()
	body, err := io.ReadAll(io.LimitReader(result.Body, 5_000_001))
	if err != nil || len(body) > 5_000_000 {
		output.Error, output.ErrorKind = "invalid response size", "response"
		if ctx.Err() != nil {
			output.ErrorKind = "timeout"
		}
		return output
	}
	output.Status, output.Body = result.StatusCode, body
	output.Headers = make(map[string]string)
	for key := range result.Header {
		if strings.EqualFold(key, "Set-Cookie") {
			continue
		}
		output.Headers[key] = result.Header.Get(key)
	}
	return output
}
