// The NDJSON protocol carries responses in memory; no profile files or logs are written.
package main

import (
	"bufio"
	"encoding/json"
	"io"
	"os"
	"sync"
)

type request struct {
	ID        uint64 `json:"id"`
	URL       string `json:"url"`
	UserAgent string `json:"user_agent"`
}

type response struct {
	ID      uint64            `json:"id"`
	Status  int               `json:"status"`
	Headers map[string]string `json:"headers,omitempty"`
	Body    []byte            `json:"body,omitempty"`
	Error   string            `json:"error,omitempty"`
}

// run multiplexes at most 128 requests and serializes complete response frames.
func run(input io.Reader, output io.Writer) {
	client := nativeClient()
	defer client.CloseIdleConnections()
	scanner := bufio.NewScanner(input)
	scanner.Buffer(make([]byte, 4096), 65_536)
	encoder := json.NewEncoder(output)
	slots := make(chan struct{}, 128)
	var workers sync.WaitGroup
	var writer sync.Mutex
	for scanner.Scan() {
		var item request
		if json.Unmarshal(scanner.Bytes(), &item) != nil {
			return
		}
		slots <- struct{}{}
		workers.Add(1)
		go func(item request) {
			defer workers.Done()
			defer func() { <-slots }()
			result := probe(client, item)
			writer.Lock()
			_ = encoder.Encode(result)
			writer.Unlock()
		}(item)
	}
	workers.Wait()
}

func main() { run(os.Stdin, os.Stdout) }
