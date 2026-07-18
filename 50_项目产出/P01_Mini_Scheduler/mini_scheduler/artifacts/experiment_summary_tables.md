# Mini Scheduler Experiment Summary Tables

> Generated reference artifact, not learner-owned work or research evidence.

The deterministic teaching fixtures use explicit actual durations. In the standard fixtures, estimates equal actual durations, so predicted and oracle SJF are expected to match. The prediction-error counterexample is the only table below that intentionally separates them. Percentiles use the nearest-rank definition.

## High Load Strategy Comparison

| strategy | task_count | average_wait_time | max_wait_time | p95_wait_time | p99_wait_time | average_turnaround_time | max_ready_queue_length | worker_utilization |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fifo | 52.00 | 48.71 | 101.45 | 97.70 | 101.45 | 51.68 | 30.00 | 0.97 |
| priority | 52.00 | 37.02 | 121.45 | 112.95 | 121.45 | 39.98 | 26.00 | 0.97 |
| predicted_sjf | 52.00 | 26.04 | 121.45 | 108.45 | 121.45 | 29.01 | 26.00 | 0.97 |
| oracle_sjf | 52.00 | 26.04 | 121.45 | 108.45 | 121.45 | 29.01 | 26.00 | 0.97 |
| cost_aware | 52.00 | 26.51 | 121.45 | 108.45 | 121.45 | 29.48 | 26.00 | 0.97 |

## Worker Count Comparison

| strategy | task_count | average_wait_time | max_wait_time | p95_wait_time | p99_wait_time | average_turnaround_time | max_ready_queue_length | worker_utilization | worker_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fifo | 52.00 | 48.71 | 101.45 | 97.70 | 101.45 | 51.68 | 30.00 | 0.97 | 1.00 |
| fifo | 52.00 | 19.74 | 44.40 | 42.80 | 44.40 | 22.71 | 28.00 | 0.86 | 2.00 |
| fifo | 52.00 | 5.31 | 17.20 | 15.70 | 17.20 | 8.28 | 21.00 | 0.61 | 4.00 |
| fifo | 52.00 | 0.88 | 3.70 | 3.50 | 3.70 | 3.85 | 10.00 | 0.30 | 8.00 |
| priority | 52.00 | 37.02 | 121.45 | 112.95 | 121.45 | 39.98 | 26.00 | 0.97 | 1.00 |
| priority | 52.00 | 14.00 | 55.85 | 50.60 | 55.85 | 16.96 | 23.00 | 0.83 | 2.00 |
| priority | 52.00 | 4.22 | 19.20 | 17.70 | 19.20 | 7.18 | 19.00 | 0.61 | 4.00 |
| priority | 52.00 | 0.79 | 4.75 | 4.00 | 4.75 | 3.76 | 9.00 | 0.30 | 8.00 |
| predicted_sjf | 52.00 | 26.04 | 121.45 | 108.45 | 121.45 | 29.01 | 26.00 | 0.97 | 1.00 |
| predicted_sjf | 52.00 | 9.75 | 54.10 | 49.10 | 54.10 | 12.71 | 20.00 | 0.85 | 2.00 |
| predicted_sjf | 52.00 | 3.25 | 19.15 | 15.40 | 19.15 | 6.22 | 16.00 | 0.61 | 4.00 |
| predicted_sjf | 52.00 | 0.67 | 4.95 | 3.50 | 4.95 | 3.63 | 8.00 | 0.30 | 8.00 |
| oracle_sjf | 52.00 | 26.04 | 121.45 | 108.45 | 121.45 | 29.01 | 26.00 | 0.97 | 1.00 |
| oracle_sjf | 52.00 | 9.75 | 54.10 | 49.10 | 54.10 | 12.71 | 20.00 | 0.85 | 2.00 |
| oracle_sjf | 52.00 | 3.25 | 19.15 | 15.40 | 19.15 | 6.22 | 16.00 | 0.61 | 4.00 |
| oracle_sjf | 52.00 | 0.67 | 4.95 | 3.50 | 4.95 | 3.63 | 8.00 | 0.30 | 8.00 |
| cost_aware | 52.00 | 26.51 | 121.45 | 108.45 | 121.45 | 29.48 | 26.00 | 0.97 | 1.00 |
| cost_aware | 52.00 | 9.75 | 54.10 | 49.10 | 54.10 | 12.71 | 20.00 | 0.85 | 2.00 |
| cost_aware | 52.00 | 3.25 | 19.15 | 15.40 | 19.15 | 6.22 | 16.00 | 0.61 | 4.00 |
| cost_aware | 52.00 | 0.67 | 4.95 | 3.50 | 4.95 | 3.63 | 8.00 | 0.30 | 8.00 |

## Prediction Error Counterexample

| strategy | task_count | average_wait_time | max_wait_time | p95_wait_time | p99_wait_time | average_turnaround_time | max_ready_queue_length | worker_utilization |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fifo | 24.00 | 46.85 | 89.70 | 88.80 | 89.70 | 50.85 | 22.00 | 1.00 |
| predicted_sjf | 24.00 | 61.35 | 92.80 | 92.20 | 92.80 | 65.35 | 22.00 | 1.00 |
| oracle_sjf | 24.00 | 30.35 | 85.00 | 76.40 | 85.00 | 34.35 | 22.00 | 1.00 |

## Cost Weight Comparison

| strategy | task_count | average_wait_time | max_wait_time | p95_wait_time | p99_wait_time | average_turnaround_time | max_ready_queue_length | worker_utilization |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| default | 30.00 | 41.97 | 104.40 | 99.60 | 104.40 | 45.83 | 23.00 | 0.92 |
| duration_dominant | 30.00 | 37.30 | 104.40 | 99.60 | 104.40 | 41.17 | 23.00 | 0.92 |
| token_dominant | 30.00 | 48.63 | 110.80 | 110.60 | 110.80 | 52.50 | 23.00 | 0.92 |
| priority_dominant | 30.00 | 46.63 | 104.40 | 99.60 | 104.40 | 50.50 | 26.00 | 0.92 |

## Aging Protection Comparison

| strategy | task_count | average_wait_time | max_wait_time | p95_wait_time | p99_wait_time | average_turnaround_time | max_ready_queue_length | worker_utilization |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| no_aging | 30.00 | 48.63 | 110.80 | 110.60 | 110.80 | 52.50 | 23.00 | 0.92 |
| gentle_aging | 30.00 | 48.63 | 110.80 | 110.60 | 110.80 | 52.50 | 23.00 | 0.92 |
| strong_aging | 30.00 | 42.66 | 104.40 | 100.80 | 104.40 | 46.53 | 25.00 | 0.92 |

## Task Type Breakdown

| task_type | task_count | average_wait_time | max_wait_time | p95_wait_time | average_turnaround_time | experiment |
| --- | --- | --- | --- | --- | --- | --- |
| batch_heavy | 5.00 | 94.80 | 104.40 | 104.40 | 100.80 | duration_dominant |
| cheap_medium | 5.00 | 9.60 | 13.20 | 13.20 | 12.60 | duration_dominant |
| long_low_token | 5.00 | 59.40 | 73.00 | 73.00 | 67.40 | duration_dominant |
| low_priority_short | 5.00 | 0.40 | 0.40 | 0.40 | 1.60 | duration_dominant |
| short_high_token | 5.00 | 32.40 | 40.80 | 40.80 | 33.40 | duration_dominant |
| urgent_medium | 5.00 | 27.20 | 32.80 | 32.80 | 31.20 | duration_dominant |
| batch_heavy | 5.00 | 90.80 | 100.40 | 100.40 | 96.80 | token_dominant |
| cheap_medium | 5.00 | 9.60 | 13.20 | 13.20 | 12.60 | token_dominant |
| long_low_token | 5.00 | 35.40 | 49.00 | 49.00 | 43.40 | token_dominant |
| low_priority_short | 5.00 | 0.40 | 0.40 | 0.40 | 1.60 | token_dominant |
| short_high_token | 5.00 | 88.40 | 110.80 | 110.80 | 89.40 | token_dominant |
| urgent_medium | 5.00 | 67.20 | 72.80 | 72.80 | 71.20 | token_dominant |
| batch_heavy | 5.00 | 94.80 | 104.40 | 104.40 | 100.80 | priority_dominant |
| cheap_medium | 5.00 | 23.60 | 27.20 | 27.20 | 26.60 | priority_dominant |
| long_low_token | 5.00 | 55.40 | 69.00 | 69.00 | 63.40 | priority_dominant |
| low_priority_short | 5.00 | 35.40 | 35.40 | 35.40 | 36.60 | priority_dominant |
| short_high_token | 5.00 | 64.40 | 80.80 | 80.80 | 65.40 | priority_dominant |
| urgent_medium | 5.00 | 6.20 | 11.80 | 11.80 | 10.20 | priority_dominant |

## Aging Task Type Breakdown

| task_type | task_count | average_wait_time | max_wait_time | p95_wait_time | average_turnaround_time | experiment |
| --- | --- | --- | --- | --- | --- | --- |
| batch_heavy | 5.00 | 90.80 | 100.40 | 100.40 | 96.80 | no_aging |
| cheap_medium | 5.00 | 9.60 | 13.20 | 13.20 | 12.60 | no_aging |
| long_low_token | 5.00 | 35.40 | 49.00 | 49.00 | 43.40 | no_aging |
| low_priority_short | 5.00 | 0.40 | 0.40 | 0.40 | 1.60 | no_aging |
| short_high_token | 5.00 | 88.40 | 110.80 | 110.80 | 89.40 | no_aging |
| urgent_medium | 5.00 | 67.20 | 72.80 | 72.80 | 71.20 | no_aging |
| batch_heavy | 5.00 | 68.80 | 104.40 | 104.40 | 74.80 | strong_aging |
| cheap_medium | 5.00 | 8.16 | 13.20 | 13.20 | 11.16 | strong_aging |
| long_low_token | 5.00 | 57.40 | 93.00 | 93.00 | 65.40 | strong_aging |
| low_priority_short | 5.00 | 4.00 | 9.40 | 9.40 | 5.20 | strong_aging |
| short_high_token | 5.00 | 52.40 | 92.20 | 92.20 | 53.40 | strong_aging |
| urgent_medium | 5.00 | 65.20 | 100.80 | 100.80 | 69.20 | strong_aging |
