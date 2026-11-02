# Local benchmark results

Measured on 21 October 2026 using the live Docker API/worker, PostgreSQL/pgvector and local Ollama. This is a synthetic pipeline baseline, not a measurement of business accuracy or an official public benchmark score.

Public aggregate measurements are available as [JSON](docs/benchmarks/pilot-20261021-summary.json) and [CSV](docs/benchmarks/pilot-20261021-summary.csv). The original machine also retains a private HTML report and full measurements under `output/benchmarks/pilot-20261021-final/`, with the original run under `output/benchmarks/pilot-20261021/`. These private artifacts are ignored by Git; generate your own using [BENCHMARKING.md](BENCHMARKING.md). The separate derived report contains corrected advisory judge annotations.

## Quality comparison

Ten small authored PDFs, forty questions, four configurations, one repeat and top-k five: 160 scored requests. There are 33 answerable questions and seven expected refusals, including a user instruction override attempt. The corpus includes a scan, a ruled table, distractors, follow-ups, multi-document questions, document instruction injection and a replaced document version. The isolated fixture workspace remains available on the original installation; its identifier is recorded in the private manifest.

Generation used `qwen2.5:7b-instruct` (Q4_K_M), embeddings used `nomic-embed-text`, and generation context was 4096 with a 1024-token output limit. Model digests, document/version IDs, source hashes and engine fingerprints are recorded in the report. The host reported Windows 11, twelve logical CPUs and Python 3.12.7. Retrieval/answer measurements ran sequentially, without a competing benchmark workload.

| Configuration | Strict fixture passes | Final Recall@5 | nDCG@5 | Warm median | Warm p95 |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL full-text keyword search | 27/40 (67.5%) | 60.6% | 0.6061 | 0.735 s | 1.096 s |
| Vector | 38/40 (95%) | 100% | 0.9955 | 0.914 s | 1.113 s |
| Hybrid | 38/40 (95%) | 100% | 0.9955 | 0.930 s | 1.146 s |
| Hybrid with local-model reranking | 28/40 (70%) | 100% | 0.9507 | 1.211 s | 1.687 s |

All 160 requests completed without API/stream errors. All configurations correctly refused the seven unsupported/override questions under the disclosed refusal heuristic. Vector, hybrid and reranked hybrid had 100% expected-fact string coverage and 95.45% gold-evidence citation coverage. These are automatic proxies, not semantic or human-reviewed accuracy. No invalid filename/page citation references were observed.

Observed failures:

- Keyword search missed annotated evidence in thirteen answerable cases and consequently refused them. The PostgreSQL `websearch_to_tsquery` baseline is strict full-text search, not BM25. Twenty keyword requests had empty context, including supported questions, so its latency cannot be read as successful-generation speed.
- Vector and hybrid both failed `alias-coordinator` and `followup-orion`: the factual strings and final evidence were present, but citations omitted one of the required supporting pages. Their strict pass rate was therefore 95%, despite perfect measured retrieval recall.
- Reranking fell back to fused order on twelve requests because its output could not be accepted. Both citation failures occurred among these fallbacks. Strict pass rate penalizes the requested reranker failing even when the fallback answer contains the expected facts. Reranking also lowered nDCG in this run.

The first quality request took 124.14 seconds with the generation model initially absent. Warm timing groups exclude that request. The reranking run also contained a 10.48-second completed request; median and p95 do not describe every tail event. Do not compare these short synthetic answers with long business answers or treat a small-run p95 as a service guarantee.

The practical default remains hybrid without reranking. Vector tied hybrid on this small corpus; there is no measured quality gain from hybrid here. Improve citation completeness and reranker reliability, then compare on a held-out, human-reviewed domain dataset before changing the default.

## Extraction and security

- The one English raster scan had normalized CER 0 and WER 0, measured against ingestion's saved OCR text.
- The one ruled table had 100% annotated cell-string accuracy. This is not TEDS or a test of complex layouts, merged cells or multilingual scans.
- The enterprise regression suite passed: verification/recovery/session revocation, invitations, document ACLs/direct SQL row policies, historical answer redaction/replay, private chat tools, raster OCR provenance, SSO local-password/recovery restrictions, expired tokens and trace correlation. The private captured log is `output/benchmarks/pilot-20261021-final/security.log`. It is a regression suite, not a security certification.

## Advisory judge and human review

Eight selected hybrid answers were judged locally. The original prompt-only contract failed validation on all eight because the model copied an example coverage-array length. The judge now uses an exact JSON schema. Rejudging the frozen answers produced eight valid outputs: faithfulness, correctness precision/recall/F1 and citation precision/completeness were all 1.0 for that selected subset. Prior errors remain in the derived report; original request measurements were not rerun or replaced.

These eight simple cases exclude the observed citation failures and use the same model as answerer and judge. They are uncalibrated advisory results and must not be reported as overall correctness. Human-reviewed answer count is zero; human accuracy and judge calibration remain unscored. The review export/import was checked with blank labels and correctly returned no human score. Supply independent human labels using the guide before relying on model judging.

## Real-generation capacity

The first eighteen-request probe completed 6/6, 4/6 and 2/6 requests at concurrency 1, 2 and 4; the other requests received HTTP 503. Its first serial request took 80.125 seconds after the judge workload, despite the model being reported loaded. A loaded model alone does not guarantee a warm request, especially when context configuration changes. The delay's precise cause was not instrumented. Private original results at `output/benchmarks/load-20261021/load.json` retain that event.

A second probe ran after generation was warm, with a fresh isolated reader and no competing model workload. Every completed request had document context and performed real generation; no errors were retried away.

| Concurrent clients | Completed / attempted | HTTP 503 busy | Completed requests/s | Completed latency median / p95 |
| --- | --- | --- | --- | --- |
| 1 | 6/6 | 0 | 1.163 | 0.688 / 0.930 s |
| 2 | 3/6 | 3 | 1.038 | 0.782 / 0.894 s |
| 4 | 2/6 | 4 | 0.696 | 0.938 / 1.106 s |

The public aggregate JSON includes the warm-load measurements. Full private results remain under `output/benchmarks/load-warm-20261021/`. The model concurrency limit is one, so higher offered concurrency causes controlled rejection rather than more parallel generation. This small burst probe does not establish sustained production capacity. Model memory snapshots are included; peak host/GPU memory and tokens/second are not measured.

## Validation and remaining evaluation work

Twenty-three backend unit tests passed, including metric mathematics, fixture/page annotations, stale-version rejection, malformed judge output and calibration behavior. The live enterprise suite passed. Report generation, blind-review export/import and identity comparison were checked. Existing CI discovers the new unit tests; a remote GitHub workflow execution has not been claimed.

Public BEIR, RAGBench, ALCE and OmniDocBench datasets were not downloaded or run. Representative enterprise quality still requires human-reviewed questions and relevance labels, independent judge calibration, larger/more varied documents, repeated held-out measurements and deployment-specific sustained load testing. The implemented tools support private annotated corpora and paired run comparisons for that next stage.
