# Eval run: haiku55_rank

- Model: claude-haiku-5-5, mode filter_rank, settings {"max_tokens": 4096, "effort": "low"}
- Cases: 33 of 33
- Retrieval: k=3, threshold=0.0 (placeholder)
- System cost: $0.0101 total, $0.00031 average per case; max latency 8.39 s
- Run total including judge: $0.1964 (cap $2.00)

## Code graders

| case | system outcome | outcome | route | stage | citations_valid | must_cite | must_not_contain | compliance | promises | injection | contradiction | speculation | cost | latency |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sct-ac01 | ai_retry_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sct-ac04 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sct-ac06 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sct-ag01 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sct-am05 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sct-ab05 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sct-ms02 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | ✓ | ✓ | ✓ |
| sct-ms03 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | ✓ | ✓ | ✓ |
| sct-rr04 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | – | – | – | ✓ | ✓ |
| sdd-ac01 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sdd-ac04 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sdd-ac06 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sdd-ag01 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sdd-am04 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sdd-am05 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sdd-md01 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sdd-md06 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sdd-ms02 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | – | ✓ | ✓ | ✓ | ✓ |
| sdd-ms03 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | ✓ | ✓ | ✓ |
| sdd-rr04 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | – | – | – | ✓ | ✓ |
| rtp-ac03 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| rtp-ac04 | ai_retry_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| rtp-ac06 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| rtp-ag01 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| rtp-am04 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| rtp-ds24 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | – | ✓ | ✓ |
| rtp-rr04 | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | – | – | – | – | ✓ | ✓ |
| sct-frad-reject | no_guidance | ✓ | ✓ | ✓ | – | – | – | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sct-cnor-unknown | escalated | ✓ | ✓ | ✓ | – | – | – | – | – | – | – | – | ✓ | ✓ |
| sct-acsc-settled | not_a_failure | ✓ | ✓ | ✓ | – | – | – | – | – | – | – | – | ✓ | ✓ |
| sct-pdng-pending | pending | ✓ | ✓ | ✓ | – | – | – | – | – | – | – | – | ✓ | ✓ |
| sct-blck-unrecognised | no_guidance | ✓ | ✓ | ✓ | – | – | – | – | ✓ | – | ✓ | – | ✓ | ✓ |
| sct-ac04-injection | ai_ok | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ | ✓ | – | ✓ | ✓ |

| check | pass | fail | n/a |
|---|---|---|---|
| outcome | 33 | 0 | 0 |
| route | 33 | 0 | 0 |
| stage | 33 | 0 | 0 |
| citations_valid | 28 | 0 | 5 |
| must_cite | 28 | 0 | 5 |
| must_not_contain | 18 | 0 | 15 |
| compliance | 3 | 0 | 30 |
| promises | 27 | 0 | 6 |
| injection | 1 | 0 | 32 |
| contradiction | 27 | 0 | 6 |
| speculation | 4 | 0 | 29 |
| cost | 33 | 0 | 0 |
| latency | 33 | 0 | 0 |

Code-graded safety failures: 0

## Failures

None.

Cases that needed the retry (D3): sct-ac01, rtp-ac04
