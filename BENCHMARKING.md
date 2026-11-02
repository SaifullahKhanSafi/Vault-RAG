# Benchmarking the RAG engine

The completed local comparison and observed failures are in [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md).

Run from the project root in VS Code's PowerShell terminal. Docker Desktop and Ollama must be running. The benchmark calls the real authenticated API and preserves existing documents. It creates a separate synthetic workspace, approved test actor, fixture documents and private conversations; those records remain available for inspection.

## Start the stack

```powershell
cd D:\RAG
docker compose up -d --build
```

The benchmark reads local test credentials from `.env`. If you changed the initial administrator password, set `RAG_EVAL_EMAIL` and `RAG_EVAL_PASSWORD` in your terminal environment to the correct account. Keep secrets out of command-line arguments. The fixture run needs an account allowed to create workspaces and provision its isolated benchmark actor.

Avoid editing backend files or running another model workload during measurement. Development auto-reload and competing requests can interrupt or distort a run. Do not disable normal authentication, row policies, CSRF or request limits for the test.

## Quick check, then full pilot

```powershell
.\backend\venv\Scripts\python.exe tools/benchmark.py --fixture --configs hybrid --limit 5
```

This indexes ten small PDFs and tests five questions. For all four configurations and all forty questions:

```powershell
.\backend\venv\Scripts\python.exe -u tools/benchmark.py --fixture --security
```

Configurations are keyword-only (`lexical`, using PostgreSQL full-text ranking), vector-only, hybrid reciprocal rank fusion, and hybrid with local-model reranking. The keyword baseline is not BM25. The benchmark freezes the questions, document/version references, model names/digests, backend code fingerprint and environment metadata.

Expect several minutes for upload pacing and the full comparison; the first model load can take several additional minutes. Requests start at least 3.2 seconds apart by default to respect the per-user budget. Follow-up setup turns also use the normal query budget. Leave the interval at its default for quality evaluation. HTTP failures, timeouts and stream errors remain in the report rather than being silently retried.

Each run prints its output location:

```text
output/benchmarks/<run-id>/index.html
```

Open `index.html` in your browser. `summary.csv` opens in Excel; `cases.csv` contains answers and failure categories; `report.json` contains full measurements and context; `dataset.json` freezes annotations; `manifest.json` identifies the isolated fixture workspace and source hashes. Report text and CSV cells are escaped for display. These files can contain private source text, so the benchmark output directory is ignored by Git.

Use a new directory with `--output` to retain an explicit baseline. Existing report directories are not overwritten.

## What the scores mean

| Result | Definition |
| --- | --- |
| Candidate Recall@5/@10 | Fraction of annotated evidence units found before reranking. |
| Final recall/precision/MRR/nDCG | Evidence coverage, noise and order in the actual passages supplied to answer generation, after reranking. |
| Expected-fact coverage | Fraction of authored fact groups whose acceptable strings appear in the answer. A transparent proxy, not semantic correctness. |
| Gold evidence citation coverage | Fraction of expected evidence pages both present in context and referenced in the answer. |
| Reference validity | Whether citation filename/page pairs exist in the provided context. It does not establish claim support. |
| Correct abstention / false refusal | Whether unsupported questions are declined and supported questions are answered, using disclosed phrase heuristics. |
| Strict fixture pass rate | All applicable automatic fact, evidence, citation, refusal and injection checks pass. It is not business accuracy. |
| OCR CER/WER | Character/word error rates after Unicode, case and whitespace normalization against the authored scan text. |
| Table-cell accuracy | Correct row/column cell strings divided by annotated cells, using the best matching extracted table. Not TEDS. |
| TTFT | HTTP send to first nonempty answer token; status and keep-alive messages do not count. |
| Latency median/p95 | Observed completed-request timings; errors are separately counted. Cold/warm groups use the model-loaded state observed before each request. |

Evidence units are unique filename/page pairs, optionally requiring specific source text. This prevents a different chunk from the right page counting as the answer passage. Version IDs are checked. A repeated hit to the same evidence unit receives no extra gain. Precision@k uses denominator k even when fewer than k passages are returned. Relevance precision assumes complete judgments; mark `judgments_complete=false` when your annotations are incomplete and interpret it as precision relative to labeled evidence.

Scores are averaged across questions with applicable labels. Unsupported questions have no retrieval ground truth and are excluded from retrieval averages, not assigned perfect recall. Failed requests count as failed automatic quality cases. Latency summaries include completed requests only; check error rate, context-present latency and empty-context completion counts together. Fast refusals are not evidence of fast successful generation.

The 40-case pilot is agent-authored and synthetic. It includes facts, exact identifiers, paraphrases, follow-ups, multiple documents, tables, scans, unsupported questions, source/user injection and an old/new release version. It is a pipeline benchmark, not a human-reviewed enterprise test set or an official BEIR/RAGBench leaderboard run.

## Optional claim-level judging

Use a local model already installed in Ollama:

```powershell
.\backend\venv\Scripts\python.exe -u tools/benchmark.py --fixture --configs hybrid --judge-model qwen2.5:7b-instruct --judge-limit 8
```

The judge receives the answer, reviewed/authored reference facts and the full final context. It proposes factual claims, evidence support, correctness where established by the reference, and citation support. Reports label faithfulness, correctness precision/recall/F1 and citation precision/completeness as **advisory and uncalibrated**. Invalid judge responses are recorded as errors, not converted to perfect or zero quality scores. The default example uses the answer model as judge, so self-grading bias is a material limitation. Prefer an independent locally installed judge and calibrate it against human labels.

Judging is outside response-latency measurements. Only the explicitly requested configuration/subset is judged; those scores do not represent all questions or configurations.

## Use your own documents and reviewed questions

Create a private JSON dataset using `evals/benchmark.example.json`. Fill in actual questions, acceptable facts and the exact supporting PDF pages/text. Use a representative set of documents with distractors and unsupported questions. Keep development questions and held-out questions separate; related paraphrases/follow-ups should share a `family` so confidence estimates do not treat them as independent.

Upload/index the corpus normally, then find its workspace UUID using `/workspaces` or the browser Network tab. Run:

```powershell
.\backend\venv\Scripts\python.exe tools/benchmark.py --dataset evals/private/company.json --validate-only
.\backend\venv\Scripts\python.exe -u tools/benchmark.py --dataset evals/private/company.json --workspace YOUR_WORKSPACE_UUID
```

Omit version IDs to bind labels to the current active document versions at run time; supply an explicit ID to require a particular active version. The runner rejects missing documents, unindexed versions, duplicate cases and malformed annotations instead of quietly scoring an unrelated corpus. It evaluates accessible documents only. With a custom dataset it does not upload, replace, delete or change permissions on your documents.

Optional `extraction_references` compare OCR text or a table against the extraction saved during ingestion. Old versions indexed before migration 007 have no extraction diagnostics and are marked unavailable; upload/reindex a separate staging version to assess them. Benchmark metrics use the indexed extraction, not a later reparse.

Public BEIR/RAGBench/ALCE/OmniDocBench data has not been downloaded or evaluated by the pilot. Adapting a public dataset requires its complete retrieval corpus, relevance labels and appropriate provenance. Do not call results on a filtered corpus official benchmark scores. The current engine accepts PDFs; existing text datasets require an explicit corpus adapter before an end-to-end PDF test.

## Repeat, compare and review

`--repeats 3` repeats every question/configuration. The report includes paired differences from hybrid with a seeded question-family cluster bootstrap interval. On this small synthetic corpus, those intervals are exploratory.

Compare two runs on the same frozen case set and verify the corpus/version snapshots before attributing changes to the engine:

```powershell
.\backend\venv\Scripts\python.exe tools/benchmark_compare.py --baseline output/benchmarks/BASELINE/report.json --current output/benchmarks/CANDIDATE/report.json
```

`--fail-on-regression` optionally exits nonzero for a negative paired pass-rate interval entirely below zero, a failed security suite, request/stream failures or invalid citation references. `--fail-on-errors` on the main runner only gates request/stream errors and the optional security suite. Neither invents a universal 90-percent industry threshold. A security suite passing means no failures were observed in those checks, not proof of no vulnerabilities.

Export blind human-review rows without displaying judge predictions:

```powershell
.\backend\venv\Scripts\python.exe tools/benchmark_review.py --report output/benchmarks/RUN/report.json --export output/benchmarks/RUN/review.csv
```

Review the answer/claim, reference facts and evidence. Fill only human label/reviewer/notes columns using yes/no/unknown. Preserve case IDs and frozen text. Then import:

```powershell
.\backend\venv\Scripts\python.exe tools/benchmark_review.py --report output/benchmarks/RUN/report.json --labels output/benchmarks/RUN/review.csv
```

Unreviewed labels remain unscored. Calibration reports agreement, Cohen's kappa where defined, and precision/recall for the judge's unsupported/incorrect warning flags. An answer-level human correctness rate is reported only for supplied human labels. Do not create human labels by copying model predictions.

To regenerate HTML/CSV summaries with an updated renderer while preserving original measurements:

```powershell
.\backend\venv\Scripts\python.exe tools/benchmark_report.py --report output/benchmarks/RUN/report.json --output output/benchmarks/RUN-summary
```

Add `--judge-model qwen2.5:7b-instruct --judge-limit 8` to judge saved answers without rerunning retrieval or generation. The new report retains the source-report hash, previous judge annotations and judge-code hash. The judge uses a JSON schema with exactly one coverage label per reference fact; rejected output remains an error.

## Real-generation load probe

Run after quality evaluation has completed, using a staging/fixture workspace with accessible documents:

```powershell
.\backend\venv\Scripts\python.exe -u tools/benchmark_load.py --workspace YOUR_WORKSPACE_UUID
```

This provisions an isolated reader actor and attempts six real questions at concurrency 1, 2 and 4. It records successful requests/second, latency/TTFT, model memory snapshots, empty-context completions and all HTTP 503/429/errors. The engine's default model concurrency is one, so overload rejection is expected; rejected calls are not counted as successful throughput. This small probe is not a production capacity certification. Peak host RAM/GPU utilization and generated tokens/second are not measured by this probe.

`--cold-start` explicitly unloads the local chat model first and can affect other users; it is opt-in. Quality runs merely observe model-loaded status and do not force unloads. Use larger representative load tests on your intended deployment hardware before setting service objectives.

## References

- [BEIR metrics](https://github.com/beir-cellar/beir/wiki/Metrics-available): ranking/retrieval evaluation.
- [Ragas metric definitions](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/): support, relevance and correctness dimensions.
- [ALCE](https://github.com/princeton-nlp/ALCE): citation-quality evaluation.
- [OmniDocBench](https://github.com/opendatalab/OmniDocBench): document-parsing benchmarks.

The tools here implement local metrics and an optional Ollama judge; they do not install these external benchmark frameworks or send documents to a paid evaluator.
