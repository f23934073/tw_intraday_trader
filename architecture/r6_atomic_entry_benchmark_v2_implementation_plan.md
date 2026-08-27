# R6 Atomic ENTRY Benchmark Revision 2 — Implementation Plan

```text
Document status: G0 AMENDMENT A1 / PASSED / CONTRACT FROZEN
R5 v2: COMPLETE / RESEARCH REJECT
R6 G1: PASSED
R6 G2: PASSED
R6 G3: BLOCKED ON A1 IMPLEMENTATION
R6 formal replay: 0 / 7 / NOT AUTHORIZED
Local Paper / Broker / Real-money: PROHIBITED
```

## 1. Objective

R6 answers one narrow research question:

> Under one immutable historical Dataset and identical one-lot execution,
> exit, and cost semantics, which of the seven remaining atomic ENTRY signals
> has positive standalone historical edge?

R6 is not a portfolio Backtest, capital-allocation test, parameter search,
pairwise winner test, Strategy Set composition test, or promotion workflow.
Every signal episode is economically independent; overlapping episodes are
allowed and no shared cash/equity account exists.

The Dataset is `research_eligible=false`. A passing result is therefore only an
exploratory research candidate. It cannot mutate Strategy Version lifecycle,
activate Local Paper, or authorize broker/real-money execution.

## 2. Authoritative inputs

### 2.1 Source and Dataset lineage

| Field | Frozen value |
|---|---|
| Source lineage Run | `run-91ad87981676414da87b928398fa43c9` |
| Source lineage role | Dataset/engine/cost provenance only; never a performance comparator |
| Dataset ID | `dataset-finmind-sponsor-sha256-88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6` |
| Dataset manifest digest | `ced1e2d7c95f8f5bd402556b022eeecdf771deedd410e3319618b9d96a141b29` |
| Dataset payload SHA-256 | `216d306d2df5ec3f6221e6e96c3998129774c966f844e9d923634d96f275c31d` |
| Dataset bars | `28,325,340` |
| Manifest date range | `2023-08-19` through `2026-08-18` |
| Observed Kbar range | `2023-08-21T09:01:00+08:00` through `2026-08-18T13:30:00+08:00` |
| Dataset binding revision | `1` |
| Research eligibility | `false` |
| Amount kind | `DERIVED_CLOSE_X_VOLUME_PROXY` |
| Amount contract digest | `12a6d73f22adb46ab8d99024812b3f0944dc03052ef92a3fbe56faba146d90fe` |

The source lineage Run's `baseline_run_id` is null. R6 may use that Run ID only
as the required durable Dataset lineage anchor. The accepted R5 replay ID must
never be placed into a `baseline_run_id` column.

### 2.2 R5 evidence boundary

R5 v2 is bound only as research-origin evidence:

| Field | Frozen value |
|---|---|
| R5 replay ID | `replay-e70d205528ef4e5f891f3d6f3c99997a` |
| R5 result digest | `420ef2dd3c3e814e0691eef0531c2c6f787789278675d092b86df3e1f9fa3347` |
| R5 postflight digest | `ca041816dd69454ce53d321fa8a78cb0188a267d5ab2b7c864eb58051a557ad9` |
| R5 disposition | `RESEARCH REJECT / HOLD / NOT ELIGIBLE` |

R5 is not the null comparator. R6 candidates are tested against zero net edge,
not against the rejected VWAP result.

## 3. Seven pre-registered hypotheses

Slot order is immutable and is not a ranking. G0 freezes a
`hypothesis_spec_digest` for every slot without inventing a Version ID. G1 binds
that specification to one exact immutable Version and only then derives the
final `hypothesis_id`. Section 3.5 freezes the non-circular dependency graph.

### 3.1 Frozen slot matrix

| Slot | Strategy | Exact parameters | Version admission | Configuration digest | Feature Request identity digest |
|---:|---|---|---|---|---|
| 1 | `breakout_previous_high_entry` | `buffer_bps=0`, `09:02-12:45` | Version `ecbfe315-0a0c-400c-9005-d33bb1db7e62` | `71c9825e3dae63177c6895245fe0d56e097b83d2eb755eac93ca812a7dfa6958` | `66c46a87f173141a540e1371c98e550c1dab9ac35ab6c0e923e229f363c76d31` |
| 2 | `rolling_return_entry` | `window_minutes=2`, `minimum_return_pct=1.5`, `09:02-12:45` | reuse Version `c95ade9e-09e2-443d-a6cd-40d576c07e6e` | `681aa02fda0e0390b626c7db1be7fa921a0b176ab45a7a5d99608e946b3f2967` | `ac362d8d7d1c2fd14f3cc56bb3fbb56154e812140a296251b701330eb5d70bcf` |
| 3 | `volume_acceleration_entry` | `window_minutes=2`, `baseline_window_count=5`, `minimum_complete_baseline_windows=4`, `baseline_method=MEDIAN`, `minimum_acceleration_ratio=1.5`, `09:10-12:45` | Version `f309ccc7-c181-4e69-a0b2-2ec53d48f008` | `56751a5c501ac430456120694ca242dc49dc1846fdbd06823817162b805cdf3d` | `99a8f980c267efed179fdef10b7a62781e8aab1a51fa3ae8fbd27ebd5059b15d` |
| 4 | `opening_range_breakout_entry` | `opening_range_minutes=15`, `breakout_buffer_pct=0.1`, `09:15-11:00` | Version `1460fd64-37c3-4bc6-a2d1-53e89fc5f3b6` | `a99f9896b877a4373c5943fba8ea80992e9f4c8723f9e93ce6bc13f0c8684b3b` | `3bd2bd03231b2198abbc0ddf5d043c3934330ef4b45f203691c6164357618770` |
| 5 | `ema_crossover_entry` | `fast_period=5`, `slow_period=20`, `09:20-12:45` | Version `31c55c80-ab96-4f81-8d5c-ed1c57ec471d` | `1f898e9c17b067ab89613a97bf7511557a28af9166474bb362db97cacae3a334` | `b32290073e444c285218a7abbd9c6634a559e7ddc42a219d1ca01084545bac52` |
| 6 | `rsi_oversold_entry` | `rsi_period=14`, `oversold_threshold=30`, `09:15-12:45` | reuse Version `701483dc-6efe-446a-aa76-1b5526c07d07` | `f90f85c194bee56b587712d213c6eda06207242ea5770d8549441f1cc98a4ed3` | `5116a29f9ff87e53e32e09683a4ebe73e68287d4e7b33662b7dde9eaa0d757ab` |
| 7 | `bollinger_lower_reentry_entry` | `bollinger_period=10`, `stddev_multiplier=2`, `09:20-12:45` | reuse Version `9cc0c8e9-2e4f-4245-9307-533a1927bbfd` | `1143834e51682660121ba74b7118e3e3dc7485da5be55e766bd33d8a45fc81ae` | `3e7a8055870bf55268619909cad4b8ddb3ca369e100ca5653b74a7ddfbee3e32` |

Bollinger period `10` is intentional because it is the immutable published
hypothesis. The current Template default period `20` is a different hypothesis
and is excluded. No parameter may be changed after this G0 candidate is
reviewed. Slots 8-20 remain unavailable.

### 3.2 Exact code and Feature identities

| Slot | Template digest | Parameter schema digest | Implementation digest | Feature Specification digest | Feature implementation digest | Feature runtime identity digest |
|---:|---|---|---|---|---|---|
| 1 | `0bb9a3ada6cf743a60eb23497deb3a216c06e2c242ee1ba7a4e326a7f5c3778a` | `be49db61ef2c085b53d5e08423db572693b0ac9a0ab12dbde814da2eeea7ddea` | `2bbd4d022933ee03a03dd29d859c3d74aba4799a4135bc8cd8acf74254506370` | `bb0e2ae9f141448e624cf94d7266fe10531bcb0918741de955a959f37a34e1f1` | `c9231f6978acd99c945f6cc13e26d70468e2203389d94b2d6b16b280e211b323` | `b184cba15c9ac4abdb6fc26448d579d6bb929fed72bc5ddec59bc62ae82f23a4` |
| 2 | `8fdfdefd8472d5dddb8ad92f82343201a36f894577f74ae293fd76f2d15ed0c2` | `ea9af619c64a56aa3d2d0d37300b93a34b30bb58e3ce1f04b8ae27f2f92048a8` | `b967d1ce8df07b9297f3c25daa5aadaa00951d8f8a1ca0398e2acbacd6e311d0` | `300ff6b95b206b1f51a71c86980994b669a970da8431f2429fff8d94da9170ab` | `a6d0f5c5074090e1eb7da2b6c0276cba8ac236829138eceaae70aa4338461c61` | `8f9810f13790f910b58e28ccc45cba2115950dd830cddfde9f36d170ff186790` |
| 3 | `b27cdb41b10fb83bbc1655a9f576503e5aced11df5f35d0739334b2c2560c156` | `ce34e90236e8008a33c5b4dccba93dc7dbd85908f46de249ed24d8fa47ee3b9d` | `3924423a7648551bb0acb9de7f23c7a6bea69050eadf9d32561767e9a84ca411` | `cdebd91a5a9091efbc16e1086ef1da7369cf38888477b723fac4cd30d2eca6c8` | `faf3cf76dfe6c724a018285bdd49fbab1c2bf5901623bf598916fa609c1d4763` | `7c8fc1c979188eb3d5dbae1e5eff94ea220b61b7f0f76f8f2bac28fb72d77dad` |
| 4 | `a711753a466229b0a78dd811fdcc68c9403c3d923067e7dd7e587ce608527d39` | `ea78ef7f319982f398b895edd796bd5b08ffaa689825163cb8ffd7904c762717` | `66c3002c71c74fa4fc2bddafac55d521b1397332d5600697590ce2468420dece` | `3dbd053c9dd8f6ace260911f1527f5a8e81394b8440afd4897bada380fb3c5a4` | `569a74b31344df02ad36e57e5bd1cc6a76fc956d955b50049e53ee42ec335a1b` | `f80f409f5f0971a85db2d478265d0bc4b0f46bc233d1ad8135bd6bf7c10b31b9` |
| 5 | `711503591d07722d7bc4e2ada6a5d9e675a8c0a47c3695336afeffe4a160d2a7` | `ae164be56dcba6b8f0ee6e7c1097bb27b80ba05cb204b8cbed0d5e3673c966ca` | `6124c9d0581f8f675c3723cec199e0fcbabdef0f5930c2949ba45fde5152f8a3` | `1a51e9775eeb5f526fc978a509a42d4063c5483a27fd7f881caf0963f19d0c5e` | `32ea06d3df0c01cebbec86b6b8bb55c8eb0a306f7624bfa674a70d6cbbc8755a` | `74a2ecbd575cbfffec2d83ca8aa8f3af961b0a6582247d7c6a1d1f708c80d8c5` |
| 6 | `71cee3f8fe825076fa622057b90571c560689ed1851e65f24c207f889dd8c2ab` | `99a86dffdf11d5cce6af5e3f1fabbbcd0c01dfdc8cf216cdc6caa6c38197beb9` | `80a80fc2e28811db957eef2680a96d393df5be50abff74094c982248a3a90504` | `46e3db4e2d4f91ceb16cdc5f53c7011ff2c0d711f849c5769006ea148c97fa87` | `5247c263255e55b307114afd78d88efeac48a80d6e9b08c2388a80f176221828` | `77cdb9b95a723a68fccaf42e896738e31ebc350ac6978a35e192f82cae6c4314` |
| 7 | `eac7baaaedfcb477e9f1e92c771571ec29b8167a8cc8658d699c64b6836b019a` | `1e966ad4707711e8570b02bb3d9ddd62be7cf8e4182af317c0974588b96723f3` | `8b88fe12de6cf4402e77d8b36d8e298dbc98be8c506d8e94867322b94036f627` | `e37defd1eee48c26dd0eab512809c27cdaa618403901222db5203edb13028748` | `6788cc01372ae57f88fddafafb2321909e522f71eb2aa4f5348cec537d4fd509` | `c3dc4dab9fe4b8f70928752f35a713aca53dc52f0cc1dc9cb4e4aa29b7cff0b7` |

The corresponding Feature IDs, in slot order, are
`previous_intraday_high_v1`, `rolling_return_v1`,
`rolling_volume_ratio_v1`, `opening_range_high_v1`, `ema_cross_up_v1`,
`wilder_rsi_v1`, and `bollinger_lower_reentry_v1`.

The exact normalized parameter and Backtest runtime projections are:

| Slot | Parameters digest | Exact Feature parameters | Feature parameter digest | `BACKTEST_KBAR_1M` binding |
|---:|---|---|---|---|
| 1 | `66cf030c236091daec368dbcd1dacbe8f1b29bf19573c4b5df585358be431af4` | `{}` | `44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a` | `breakout_previous_high.backtest_kbar_1m_v1` |
| 2 | `c283a54dd85520b3a68f19dc9aac7254c17ae879b69deee8b9e6b72c10d6415c` | `{"window_minutes":2}` | `70193bdbb7c94650ef504a00893e5e7a24a450fbc117673c5b6b8205cce0bf33` | `rolling_return.backtest_kbar_1m_v1` |
| 3 | `b1a6666979a64f9b0f1457c787b56b584e30e67d419b99b70fda0c23d2baa707` | `{"baseline_method":"MEDIAN","baseline_window_count":5,"minimum_complete_baseline_windows":4,"window_minutes":2}` | `7b82def9fcacf16359c2163bd89c4004aee6184c364bbd7953a37e0a38f20f13` | `volume_acceleration.backtest_kbar_1m_v1` |
| 4 | `af2e42e48b8e47502117410191b3a423291ef5ccfb4ad35e2a577c91a4a85f51` | `{"opening_range_minutes":15}` | `a1af58425af096e23ce7fd43d6e59d4cd4111982ad8e10e53fb23cb6d3b20e05` | `opening_range_breakout.backtest_kbar_1m_v1` |
| 5 | `0c10db9735b3bab95a9b8083527d2df8c26bee67e7fb1dce3e9426bd84be217c` | `{"fast_period":5,"slow_period":20}` | `54fc4555aa0c579e52620c9b4891c11d951bfd5e8caee7b9e94e15c5f4329e14` | `ema_crossover.backtest_kbar_1m_v1` |
| 6 | `27cd4d79a9563ac57c93f71e6f745e5a4ae1555c9010f60d34819475c22d4787` | `{"rsi_period":14}` | `b8794a6a35ab5b64e0770be6a7036046dab14aebda0befb7cdb9e31afd447dd2` | `rsi_oversold.backtest_kbar_1m_v1` |
| 7 | `9183e20e6957170dee129ac251752847cdcb9feda6d3b56b1440688f12303b7c` | `{"bollinger_period":10,"stddev_multiplier":"2"}` | `d8aecaaef646c38399876c0c752ee8cd9b348f0e2b697bb86dce2efe5c70bef9` | `bollinger_lower_reentry.backtest_kbar_1m_v1` |

Each strategy `parameters` object is the exact normalized object displayed in
Section 3.1: Decimal parameters are canonical strings, integers are JSON
integers, and times are `HH:MM` strings. The configuration digest uses the
existing exact Strategy Catalog projection
`{strategy_id, parameters, parameter_schema_version,
parameter_schema_digest, parameters_digest, template_digest,
implementation_digest}`.

### 3.3 G1 lifecycle and binding projections

| Slot | Status | Sequence | Last event ID | Projection digest |
|---:|---|---:|---|---|
| 1 | `PUBLISHED` | 1 | `994bdd15-8f53-469e-ae89-303cfa739d8f` | `1023d1d3a67aaf2dc8ce5dbd5990b6e9fe55f6c37a32e87516e0360f3f52913a` |
| 2 | `PUBLISHED` | 1 | `36125a0d-65c5-497e-98a1-2f1c5c6234d7` | `0dad68b96affd1c5b42439890b3ceba565091032f1c4a5fdda34ebc580bdb1b9` |
| 3 | `PUBLISHED` | 1 | `1acd5936-ab26-41ce-8575-5db54202a183` | `42322dd7b2a2a51c839458f8ffee68f6ccf5bb0f772c817dcc99b15e15152004` |
| 4 | `PUBLISHED` | 1 | `e1faf74f-19d5-4f56-9c67-4bded688f23d` | `5793e1735fed7ffca86e6f279e38a2770521a0c86f71da8dbae90bc4062e5864` |
| 5 | `PUBLISHED` | 1 | `0998a459-7bf3-460b-b2b3-760a4d7d8c68` | `ac778c92f0e05a3f6454b8f88ff4739409e502d8d4cba3a901e6b3848bbb3f2a` |
| 6 | `PUBLISHED` | 1 | `c63c55e7-6bed-439d-89ab-7f39f737ab6d` | `ffb8fca2acf1cbcadfb6acb444490d0c872fecdea0a822f57d1cb92647e4ac96` |
| 7 | `PUBLISHED` | 1 | `16ee83b3-328e-4265-ae16-0ff19c840875` | `46e2cfbbf6b3d94569ac5337a410cef56d2d62b2a793e5bc738d36fb3fc4e257` |

| Slot | Version binding digest | Hypothesis ID | Slot digest |
|---:|---|---|---|
| 1 | `37284e1b0bd6d30e4102fd433a18f22cd81a7e00330b311995236976c2e8eafb` | `7c2ec904944d7cbafa9a20081f685cc331bd97c1f8b6f1b0fc7ef5036a720327` | `dfb3a41a9ba880c61c2897690d146e52642f605f3bfa97c8c547a66f119e5c7e` |
| 2 | `3aa8f7d48a757fc4d25bd3c804380e9bf491be4e1ff961c83f7d57e9caf4153f` | `bcb3828e62bed45dec8922a33e015b0fad414ca7a99f278f87a46f30e767e90a` | `7cf95ee37e0f0b9ac2b1a18e82e1af5f10133167c21f23132633f82ec31240cf` |
| 3 | `709d2a4f25c8136f6226e83c678721d79b39b95e2e95f7ad90af9164760dceaf` | `2d66a268c796224a365aa172b90e1e0792e8df53a2ccb7e5e3f71cc3ea2d53af` | `edf3e9c08121ab4e5c71b7c57b0da3ecb139d8729711dfbc02aa06042c59a483` |
| 4 | `662d06cdd1152c9d175341a927b287facf7320f2b299ec400551defe385ffe02` | `cd9e54ae4ddf4042b6e17ac86c88ff139d2249703fea225a82eb7e62ed963376` | `2e33035647874afa21d03239a79bd8011b8b6bf68547db41d5097ee4b2419bf1` |
| 5 | `ca91422698bfcba6ab0a45e6b5ff57eb49431d08f6c7ec989c7620ba8b59cfde` | `04d0f7fbd3526c43e30ca2e673c0080b4efe905d1379ef6d7fa4306a76a54676` | `9475da43957e66dcde83469fc3a88f1489ed356add6d3cf019b4bccfc3c927ee` |
| 6 | `24af01c27c67e869a6c4e64d40619049b872f79acf04ffaafa23ba019453990c` | `80e4984414a9ce0c7066d1523d405fd10c2db4a7f65271fa53ae3ee25280e3f9` | `49c8492d106f91bc964ff0c04e62ee79ba7923c2ff6b9a9c97eac01f0f56a343` |
| 7 | `7c23db1dbf0ac0af6e9ce7ea8934b8cdfc4d6206672a0f6aaf28efa8f8804c1a` | `e998c547cb756462dbd983b6bd2b1c42401389a4cf1cfce8088bb1f204d968e7` | `fff002b9862d8d487a8e4cf9e4ac16763732d8337702d18645ddd70c4111f148` |

Matrix seal reads these projections again under the same PostgreSQL
transaction. Any status, sequence, event, or projection digest drift requires
Review; it is not automatically accepted because the Version row is immutable.

### 3.4 G1 Version admission evidence

G0 froze the exact expected configuration for slots 1, 3, 4, and 5 without
inventing database-generated Version IDs. G1 then:

1. create or reuse one Draft with the exact frozen parameters;
2. validate current Template, schema, implementation, and Feature identities;
3. Publish idempotently to lifecycle `PUBLISHED` only;
4. verify the created Version configuration digest equals this document;
5. record Version ID, publish event ID, lifecycle sequence, projection digest,
   actor, and operation result in the matrix candidate;
6. submitted the resulting candidate for independent G1 Review before any
   matrix can be sealed.

Every G1 replay now reads and rebuilds the complete durable publication graph
rather than trusting saved digests. The verifier joins the stored Template,
immutable Version, sealed Draft, lifecycle event and projection, publish
operation result, and lifecycle outbox. It reconstructs canonical parameters,
configuration, event evidence/document, publish request/result, projection,
and outbox payload before comparing every stored root. For the four new
publications it additionally enforces the frozen actor, actor session, change
note, and initial Draft revision. PostgreSQL regressions independently tamper
Version parameters, event actor, and operation result roots and require each
read to fail closed.

The four durable publish operations used actor `r6-g1-research-operator`, actor
session `r6-g1-version-admission-v1`, and change note
`R6 G1 frozen atomic-entry benchmark Version admission`:

| Slot | Publish operation ID | Publish result digest |
|---:|---|---|
| 1 | `e2d06709-ade9-47a2-9c2a-c370ea7ed493` | `f851ebd876167dfba428556e198700b88d55ac2db79bc6d833f2108aedee7602` |
| 3 | `1826d780-49b2-4329-b848-a93436ac058b` | `3ab203ae6a78ebbb8e20f74e0e0e9a3488cae9179d85379614fad1c0dcabcdbf` |
| 4 | `6b9118d6-15d0-4c86-9adf-e8e87a652d89` | `7c05790cc7e278075a4f542037e13d549b82186f9965e5dd23ca454e436afa5e` |
| 5 | `57a57560-83b2-4ab9-b93d-49cf13fed571` | `21169470682145a9f68da220ca253ea3fb20ae528b0eb19684d28a56501e161c` |

No transition to `REVIEWED`, `BACKTESTED`, or `PAPER_APPROVED` is part of R6.
The three existing Versions remain at their current lifecycle sequence; R6 does
not mutate them.

R6 seals Version identities directly. It does not create one-member Strategy
Sets because aggregation has no semantic role in an independent single-signal
replay.

### 3.5 Exact non-circular identity graph

> Historical contract note: this section through Section 13 describes the
> independently approved revision-1 matrix. The formal G3 Dataset exposed an
> incomplete same-session execution horizon before any attempt was consumed.
> Section 14 is the approved and frozen current contract. Where Section 14
> differs, it supersedes the revision-1 literals below. Its implementation and
> another G3 execution still require their separately authorized scopes.

Every digest in this section is lowercase SHA-256 over the canonical JSON bytes
of the exact projection shown. Missing or unknown keys, wrong scalar types,
numeric aliases, non-canonical Decimal strings, or a differently ordered array
fail closed. Audit actor, note, locator, idempotency key, and wall-clock fields
are never members of these projections.

The dependency order is fixed and acyclic:

```text
research_baseline_digest / family_id
  -> protocol_core_digest
  -> hypothesis_spec_digest
  -> G1 version_binding_digest / hypothesis_id
  -> ordered slot_digest values
  -> G2 benchmark_build_binding_digest
  -> matrix_core_digest / matrix_id
  -> registration_digest
  -> ledger, match, result, postflight, and family-release artifacts
```

The exact `research_baseline` keys are:

```text
schema_version, research_question_id, research_semantics_id,
source_lineage_run_id, dataset_id, dataset_manifest_digest,
dataset_bars_sha256, dataset_bar_count, dataset_binding_revision,
dataset_amount_contract_digest, r5_replay_id, r5_result_digest,
r5_postflight_digest, planned_attempts, family_alpha, adjustment_method
```

Literals are `schema_version=r6-research-baseline-v1`,
`research_question_id=ATOMIC_ENTRY_ABSOLUTE_ZERO_EDGE`,
`research_semantics_id=FIRST_TRIGGER_ONE_LOT_SAME_SESSION_V1`,
`planned_attempts=20`, `family_alpha=0.05`, and
`adjustment_method=BONFERRONI`. The Dataset/R5 values are exactly those in
Section 2. `research_baseline_digest` is the digest of this object and
`family_id` is exactly `r6-family-sha256-` plus the complete 64-hex digest.
Neither slots nor replaceable code-byte implementation digests are members, so
publishing a Version or rebuilding code cannot reset this family budget.
Counts/revisions are JSON integers; alpha/rate/threshold values are canonical
Decimal strings; IDs, digests, dates, enum values, and semantic literals are
JSON strings; arrays retain the declared order. These type rules apply to every
identity projection below.

The frozen values are:

```text
research_baseline_digest = 75f9efda41f843d95ddc324d2db7756d33415bcc8dbd274e7bc079062a7d4543
family_id = r6-family-sha256-75f9efda41f843d95ddc324d2db7756d33415bcc8dbd274e7bc079062a7d4543
```

The exact `protocol_core` keys are:

```text
schema_version, research_baseline_digest, source_lineage_run_id, dataset_id,
dataset_manifest_digest, dataset_bars_sha256, dataset_bar_count,
dataset_binding_revision, dataset_amount_contract_digest, engine_lineage,
feature_adapter_identity, input_cadence, signal_admission, entry_semantics,
entry_session_semantics, shares, exit_semantics, entry_slippage_bps,
exit_slippage_bps, commission_rate, sell_tax_rate, position_cash_semantics,
timezone, decimal_precision, decimal_rounding, research_window_start,
research_window_end, complete_quarters, family_planned_attempts, family_alpha,
adjustment_method, adjusted_one_sided_alpha, bootstrap_cluster_unit,
bootstrap_sample_count, bootstrap_sampler, bootstrap_seed_semantics,
bootstrap_quantile_index, canonical_wire_format, return_scale,
metric_contract_version, bootstrap_contract_version,
disposition_policy_version, minimum_episodes, minimum_independent_exit_dates,
minimum_mean_pre_slippage_return, minimum_mean_net_return,
minimum_return_profit_factor, minimum_bootstrap_lower_bound,
minimum_positive_complete_quarter_count, complete_quarter_count,
maximum_daily_equal_signal_drawdown, evidence_floor_comparator,
positive_edge_comparator, quarter_ratio_comparator, drawdown_comparator,
zero_episode_quarter_semantics, profit_factor_special_semantics,
pairwise_claim_semantics, exploratory_limitation
```

`schema_version=r6-protocol-core-v1`. All execution values come exactly from
Section 4; research window/quarters from Section 7.1; multiple-testing and
bootstrap values from Section 7.3; and screening thresholds from Section 7.4.
`complete_quarters` is the ordered eleven-item array in Section 7.1.
`bootstrap_sampler=SHA256_UINT64_MODULO_V1`,
`bootstrap_seed_semantics=FAMILY_ID_HYPOTHESIS_ID_BOOTSTRAP_V1`, and
`exploratory_limitation=EXPLORATORY_ONLY_NO_PROMOTION` are literals.
`protocol_core_digest` is its digest. No slot, Version, hypothesis, matrix, or
registration field is present in this object.

The remaining exact scalar/array values are:

```text
engine_lineage = backtest-engine-v2
feature_adapter_identity = backtest.completed-kbar-1m-feature-adapter-v1
input_cadence = COMPLETED_KBAR_1M_ONLY
signal_admission = FIRST_TRIGGER_PER_SLOT_SYMBOL_SESSION_V1
entry_semantics = NEXT_OBSERVED_SAME_SYMBOL_SAME_SESSION_KBAR_OPEN_STRICTLY_AFTER_SIGNAL_V1
entry_session_semantics = MUST_EQUAL_SIGNAL_SESSION_V1
shares = 1000
exit_semantics = LAST_OBSERVED_SAME_SYMBOL_ENTRY_SESSION_CLOSE_STRICTLY_AFTER_ENTRY_V1
entry_slippage_bps = 5
exit_slippage_bps = 5
commission_rate = 0.001425
sell_tax_rate = 0.003
position_cash_semantics = INDEPENDENT_EPISODES_NO_SHARED_CASH_V1
timezone = Asia/Taipei
decimal_precision = 38
decimal_rounding = ROUND_HALF_EVEN
research_window_start = 2023-08-19
research_window_end = 2026-08-18
complete_quarters = [2023Q4, 2024Q1, 2024Q2, 2024Q3, 2024Q4, 2025Q1, 2025Q2, 2025Q3, 2025Q4, 2026Q1, 2026Q2]
family_planned_attempts = 20
family_alpha = 0.05
adjustment_method = BONFERRONI
adjusted_one_sided_alpha = 0.0025
bootstrap_cluster_unit = COMPLETE_EXIT_SESSION_DATE
bootstrap_sample_count = 20000
bootstrap_quantile_index = 49
canonical_wire_format = BACKTEST_CANONICAL_JSON_V1
return_scale = 18
metric_contract_version = r6-result-summary-v1
bootstrap_contract_version = r6-daily-cluster-bootstrap-v1
disposition_policy_version = r6-absolute-zero-edge-screen-v1
minimum_episodes = 30
minimum_independent_exit_dates = 20
minimum_mean_pre_slippage_return = 0
minimum_mean_net_return = 0
minimum_return_profit_factor = 1
minimum_bootstrap_lower_bound = 0
minimum_positive_complete_quarter_count = 7
complete_quarter_count = 11
maximum_daily_equal_signal_drawdown = 0.20
evidence_floor_comparator = GTE
positive_edge_comparator = STRICT_GT
quarter_ratio_comparator = GTE
drawdown_comparator = LTE
zero_episode_quarter_semantics = INSUFFICIENT_EVIDENCE
profit_factor_special_semantics = POSITIVE_INFINITY_ONLY_WITH_POSITIVE_GAINS_AND_ZERO_LOSSES
pairwise_claim_semantics = PROHIBITED
```

The values rendered above as decimals are canonical Decimal strings in JSON;
the values rendered as counts are JSON integers.

The frozen `protocol_core_digest` is
`1cdd8bf6b30ce0d8334463665ab794b7dd3419273dd4e1c33a03357f30c44ac1`.

The exact G0 `hypothesis_spec` keys are:

```text
schema_version, slot_sequence, strategy_id, parameters,
parameters_digest, strategy_configuration_digest, template_digest,
parameter_schema_digest, strategy_implementation_digest,
backtest_runtime_binding, feature_id,
feature_parameters, feature_parameter_digest, feature_request_identity_digest,
feature_specification_digest, feature_implementation_digest,
feature_runtime_identity_digest, protocol_core_digest
```

`schema_version=r6-hypothesis-spec-v1`. The seven parameter/identity values are
exactly the rows in Sections 3.1-3.2 and the deployed runtime binding captured
by the Version inventory. `parameters` and `feature_parameters` are exact
canonical objects, not JSON strings. G0 can therefore compute all seven
`hypothesis_spec_digest` values before the four missing Version IDs exist.

| Slot | Frozen `hypothesis_spec_digest` |
|---:|---|
| 1 | `ef5541b185951aca1b83a35ff582b3489669381ec5ce99289b8f1c73b5fe08cd` |
| 2 | `c15bc531dba13bb829fc9c171c3dd8da277115e159a668e40eedf3837b864e7a` |
| 3 | `fb155920d9fcb96e777404a89ee167b1819b1965d5f502b4b9c5d28a7699e4c9` |
| 4 | `8e4a3cd8d37c072ca00157c5aec3bed184eaaa285c243202e663bac74e869dcb` |
| 5 | `858b863d0cd4abbbb563b3d52e9d1ec8b16e289b4f19b532c188716ed939f465` |
| 6 | `cd3c57ae47e6b95064f8ba561015addef4ba0201d4e44f38b66539c8f7ce1aad` |
| 7 | `c80f7edd7ce1452401a249c347c70796d807e0ba21f2440bdff3c6acb9274612` |

G1 creates the exact `version_binding` projection:

```text
schema_version, hypothesis_spec_digest, strategy_version_id, version_number,
strategy_configuration_digest, lifecycle_status, lifecycle_sequence,
lifecycle_event_id, lifecycle_projection_digest
```

`schema_version=r6-version-binding-v1` and `lifecycle_status=PUBLISHED`.
`version_binding_digest` is its digest. `hypothesis_id` is the digest of the
exact object `{schema_version, hypothesis_spec_digest,
version_binding_digest}` with literal `schema_version=r6-hypothesis-id-v1`.
The exact `slot_binding` keys are:

```text
schema_version, slot_sequence, hypothesis_id, hypothesis_spec_digest,
version_binding_digest
```

`schema_version=r6-slot-binding-v1`; `slot_digest` is its digest. The seven
`slot_digest` values are ordered strictly by `slot_sequence`.

The G0 algorithm contract is the exact object:

```json
{"calculation_precision":38,"calculation_rounding":"ROUND_HALF_EVEN","canonical_json":"BACKTEST_CANONICAL_JSON_V1","contract_version":"r6-atomic-entry-benchmark-v1","entry_semantics":"NEXT_OBSERVED_SAME_SYMBOL_SAME_SESSION_KBAR_OPEN_STRICTLY_AFTER_SIGNAL_V1","exit_semantics":"LAST_OBSERVED_SAME_SYMBOL_ENTRY_SESSION_CLOSE_STRICTLY_AFTER_ENTRY_V1","name":"independent-one-lot-atomic-entry-zero-edge-v1","return_scale":18,"shares_semantics":"EXACT_ONE_LOT_1000_SHARES_V1","signal_admission":"FIRST_TRIGGER_PER_SLOT_SYMBOL_SESSION_V1","timezone":"Asia/Taipei"}
```

Its `algorithm_contract_digest` is
`ab68f293290ca9e0263c4381ad0984133773f28112c636fe5def6db27210a200`.
Before G2 matrix seal, `algorithm_implementation_digest` is SHA-256 over an
exact ordered source manifest for `backtest/atomic_benchmark/domain.py`,
`artifacts.py`, `repository.py`, `postgres_repository.py`, `application.py`,
and `result_reader.py`; each manifest row has exact keys
`path`, `byte_count`, and `sha256`, and paths are repository-relative ASCII in
the order shown. The manifest exact keys are `schema_version` and `files`, with
literal `schema_version=r6-algorithm-source-manifest-v1`; the digest is over its
canonical JSON bytes. `persistence_schema_digest` is SHA-256 over the exact
bytes of the reviewed `backtest/migrations/016_atomic_entry_benchmark.sql`.
The exact G2 `benchmark_build_binding` keys are:

```text
schema_version, protocol_core_digest, algorithm_contract_digest,
algorithm_implementation_digest, persistence_schema_digest
```

`schema_version=r6-benchmark-build-binding-v1`;
`benchmark_build_binding_digest` is its digest. A source-byte change therefore
requires a reviewed new matrix revision inside the same family; it cannot reset
the family budget.

The exact `matrix_core` keys are:

```text
schema_version, family_id, research_baseline_digest, protocol_core_digest,
benchmark_build_binding_digest, ordered_slot_digests, registered_slots,
unavailable_slots, matrix_revision
```

Literals are `schema_version=r6-matrix-core-v1`, `registered_slots=[1..7]`,
`unavailable_slots=[8..20]`, and `matrix_revision=1`.
`matrix_core_digest` is its digest and `matrix_id` is exactly
`r6-matrix-sha256-` plus that complete 64-hex digest. The exact immutable
registration body keys are:

```text
schema_version, matrix_id, matrix_core_digest, family_id,
research_baseline_digest, protocol_core_digest,
benchmark_build_binding_digest, ordered_slot_digests, registered_slots,
matrix_revision
```

`schema_version=r6-matrix-registration-v1`; `registration_digest` is its
digest. Actor, change note, seal time, operation identity, and locators are
durable audit columns outside the registration body. Artifacts may depend on
`matrix_id`, `registration_digest`, `hypothesis_id`, and their upstream roots;
no upstream identity may depend on an artifact digest.

## 4. Common execution protocol

The revision-1 values in this section are retained as immutable history. The
current signal cutoff, execution-eligibility mask, and terminal-exit semantics
are replaced by Section 14.

The common protocol is the exact `protocol_core` object in Section 3.5. It
contains the literals below and the frozen evaluation contract, but never a
slot registration, hypothesis, Version, matrix, or artifact digest.

| Contract | Frozen value |
|---|---|
| Engine lineage | `backtest-engine-v2` |
| Feature adapter | `backtest.completed-kbar-1m-feature-adapter-v1` |
| Input cadence | completed `KBAR_1M` only |
| Signal admission | first `TRIGGERED` per `(slot, symbol, session_date)` |
| Entry | next observed same-symbol Kbar open, strictly after signal |
| Entry session | must equal signal session; cross-session entry is invalid |
| Shares | exactly `1000` |
| Exit | last observed same-symbol Kbar close in the entry session, strictly after entry |
| Entry slippage | `5` bps adverse |
| Exit slippage | `5` bps adverse |
| Commission | `0.001425` on entry and exit executed gross |
| Sell tax | `0.003` on exit executed gross |
| Position/cash | none; each episode is independent |
| Timezone | `Asia/Taipei` |
| Decimal context | precision `38`, `ROUND_HALF_EVEN` |

Cost identity and one-lot economics must reuse the accepted R5 v2 formulas:

```text
entry_fill = raw_entry_open * (1 + 5 / 10000)
exit_fill = raw_exit_close * (1 - 5 / 10000)
entry_commission = entry_fill * 1000 * 0.001425
exit_commission = exit_fill * 1000 * 0.001425
sell_tax = exit_fill * 1000 * 0.003
post_slippage_gross_pnl = (exit_fill - entry_fill) * 1000
explicit_costs = entry_commission + exit_commission + sell_tax
net_pnl = post_slippage_gross_pnl - explicit_costs
pre_slippage_return = raw_exit_close / raw_entry_open - 1
net_return = net_pnl / (raw_entry_open * 1000)
```

The exact cost identity projection is the canonical object:

```json
{"commission_rate":"0.001425","entry_slippage_bps":"5","exit_slippage_bps":"5","sell_tax_rate":"0.003","shares":1000}
```

Its `cost_identity_digest` is
`487aed133395c7e4b4dec814de80166ebaa1bf67d98a0e399a945389aea0baf7`.
Every episode/result/postflight rebuild must independently reconstruct this
projection from the sealed protocol; caller-supplied economics are prohibited.

The amount proxy remains part of Dataset lineage but none of the seven Feature
Requests consumes VWAP or turnover. Adding VWAP to a slot would be a new matrix.

## 5. Signal extraction semantics

The revision-1 incomplete-signal rule below is retained as the evidence that
stopped G3. It is not authority to skip strategy-specific failures. The current
frozen contract first constructs the common Dataset-only eligibility mask in
Section 14, then applies all seven strategies to the same eligible
symbol/session pairs.

1. Stream the canonical Dataset to EOF and independently verify exact line
   count, payload SHA-256, manifest digest, canonical bytes, ordering, parsed
   HistoricalBar projection, and session boundaries.
2. Resolve all seven exact Versions before opening any output artifact. Template,
   parameters, schema, implementation, runtime binding, Feature Request,
   Specification, Feature implementation, adapter, and lifecycle projection
   identities must match the sealed matrix.
3. Each slot owns a separate Feature runtime/state namespace. No Feature cache,
   rolling state, or result may be shared across slots.
4. All runtimes ingest the same ordered completed Kbar stream. Session switch
   evicts old session state using the existing bounded Feature owner contract.
5. Atomic strategy evaluation uses the completed bar close as current price.
   `BLOCKED`, `INSUFFICIENT_DATA`, and `NOT_TRIGGERED` never create signals.
6. The first `TRIGGERED` evaluation per slot/symbol/session creates one signal;
   subsequent bars in that tuple cannot create another signal. Feature ingestion
   continues so runtime behavior remains deterministic.
7. Signal time is the triggering Kbar timestamp. The source Kbar exact JSONL
   bytes, parsed projection, Feature input evidence, observed/threshold evidence,
   and evaluation digest are all sealed.
8. A signal without a later same-session entry bar or later same-session terminal
   close is incomplete. Any incomplete or duplicate match makes the slot
   preflight fail closed; it cannot publish performance.

This `FIRST_TRIGGER_PER_SYMBOL_SESSION` policy is the existing Backtest engine's
`entered_today` behavior. It prevents condition-style signals such as RSI from
receiving hundreds of repeated votes while event-style signals such as EMA
crossovers naturally occur once.

## 6. Canonical immutable artifacts

R6 imports the R5 v2 canonical wire format unchanged: UTF-8 without BOM,
Unicode NFC, canonical JSON with sorted keys and no whitespace, JSONL with one
canonical object plus LF per row, no blank lines, lowercase 64-hex SHA-256,
canonical Taipei timestamps without microseconds, JSON integers for counts,
and normalized Decimal strings without exponent or negative zero.

Top-level and row schemas are exact. Missing or unknown fields fail closed.
Nested `evaluation_document.observed` and `.threshold` maps are strategy-owned;
their exact canonical bytes are bound by the immutable Version implementation
digest and the row evaluation digest.

For every object whose exact schema includes its own `*_digest` field, the
digest is SHA-256 over the exact object with only that one self-digest key
omitted. Every other key, including referenced upstream digests, remains in the
projection. Row payload SHA values are SHA-256 over the concatenation of exact
canonical JSONL bytes in declared order. No implementation may omit additional
keys or hash a parsed/reformatted substitute.

### 6.1 Signal ledger row

Exact keys:

```text
schema_version, matrix_id, registration_digest, slot_sequence, hypothesis_id,
strategy_id, strategy_version_id, strategy_configuration_digest,
strategy_implementation_digest, feature_request_identity_digest, sequence,
signal_id, semantic_key, symbol, session_date, signal_at, side,
execution_horizon, current_close, source_bar_digest, evaluation_status,
evaluation_document, evaluation_digest, feature_input_evidence,
feature_input_evidence_digest
```

Literals: `schema_version=r6-signal-ledger-row-v1`, `side=ENTRY`,
`execution_horizon=INTRADAY_NEXT_BAR`, `evaluation_status=TRIGGERED`.
`sequence` starts at 1 within each slot and follows Dataset traversal order.

`signal_id` is SHA-256 of the canonical projection:

```text
schema_version, matrix_id, slot_sequence, hypothesis_id, strategy_version_id,
symbol, session_date, signal_at
```

`semantic_key` uses the same projection without `matrix_id`, but includes
`strategy_configuration_digest` and `execution_horizon`.

### 6.2 Match-plan row

Exact keys:

```text
schema_version, matrix_id, registration_digest, slot_sequence, hypothesis_id,
sequence, signal_id, semantic_key, symbol, signal_session_date, signal_at,
signal_source_bar_digest, entry_session_date, entry_at, raw_entry_open,
entry_bar_digest, exit_session_date, exit_at, raw_exit_close, exit_bar_digest,
shares, match_status
```

Literals: `schema_version=r6-match-row-v1`, `shares=1000`,
`match_status=COMPLETE`. Entry/exit raw bytes must parse to all saved symbol,
session, timestamp, and price fields.

### 6.3 Episode row

Exact keys reuse the R5 v2 economic projection with R6 lineage:

```text
schema_version, matrix_id, registration_digest, slot_sequence, hypothesis_id,
sequence, episode_id, match_id, signal_id, semantic_key, symbol, shares,
entry_session_date, entry_at, raw_entry_open, entry_fill_price,
exit_session_date, exit_at, raw_exit_close, exit_fill_price,
entry_commission, exit_commission, sell_tax, pre_slippage_price_pnl,
post_slippage_gross_pnl, explicit_costs, net_pnl, pre_slippage_return,
net_return_on_raw_entry_notional, cost_identity_digest
```

Literal `schema_version=r6-episode-row-v1`. All economic fields are rebuilt from
the match row and common cost identity on every read.

### 6.4 Manifest and postflight exact projections

Every slot has exactly one ledger manifest, match manifest, result manifest,
and postflight. There is no open-ended common-manifest inheritance.

Ledger manifest exact keys:

```text
schema_version, matrix_id, registration_digest, family_id,
research_baseline_digest, slot_sequence, hypothesis_id, strategy_id,
strategy_version_id, strategy_configuration_digest,
strategy_implementation_digest, lifecycle_sequence, lifecycle_event_id,
lifecycle_projection_digest, dataset_id, dataset_digest, dataset_bars_sha256,
dataset_binding_revision, protocol_core_digest, algorithm_contract_digest,
algorithm_implementation_digest, ledger_row_schema_version,
ledger_signal_count, ledger_rows_sha256,
ledger_signal_multiplicity_digest, ledger_manifest_digest
```

Match manifest exact keys:

```text
schema_version, matrix_id, registration_digest, family_id,
research_baseline_digest, slot_sequence, hypothesis_id, strategy_id,
strategy_version_id, strategy_configuration_digest,
strategy_implementation_digest, lifecycle_sequence, lifecycle_event_id,
lifecycle_projection_digest, dataset_id, dataset_digest, dataset_bars_sha256,
dataset_binding_revision, protocol_core_digest, algorithm_contract_digest,
algorithm_implementation_digest, ledger_manifest_digest, ledger_rows_sha256,
match_row_schema_version, signal_count, matched_entry_count,
matched_exit_count, missing_entry_count, missing_exit_count,
duplicate_match_count, match_rows_sha256,
match_signal_multiplicity_digest, match_manifest_digest
```

Result manifest exact keys:

```text
schema_version, replay_id, matrix_id, registration_digest, family_id,
research_baseline_digest, slot_sequence, hypothesis_id, strategy_id,
strategy_version_id, strategy_configuration_digest,
strategy_implementation_digest, lifecycle_sequence, lifecycle_event_id,
lifecycle_projection_digest, dataset_id, dataset_digest, dataset_bars_sha256,
dataset_binding_revision, protocol_core_digest, algorithm_contract_digest,
algorithm_implementation_digest, cost_identity_digest,
ledger_manifest_digest, match_manifest_digest, episode_row_schema_version,
episode_count, episode_rows_sha256, episode_signal_multiplicity_digest,
summary, summary_digest, result_projection_digest, result_manifest_digest
```

Postflight exact keys:

```text
schema_version, replay_id, matrix_id, registration_digest, family_id,
research_baseline_digest, slot_sequence, hypothesis_id,
expected_ledger_manifest_digest, actual_ledger_manifest_digest,
expected_match_manifest_digest, actual_match_manifest_digest,
expected_result_manifest_digest, actual_result_manifest_digest,
expected_result_projection_digest, actual_result_projection_digest,
diagnostics, recomputed_cost_identity, recomputed_summary,
acceptance_conditions, verdict, postflight_digest
```

`diagnostics` exact keys:

```text
source_bar_count, source_bars_sha256, source_eof_verified,
ledger_minus_match_count, match_minus_ledger_count,
match_minus_episode_count, episode_minus_match_count,
ledger_duplicate_count, match_duplicate_count, episode_duplicate_count,
missing_entry_count, missing_exit_count
```

`acceptance_conditions` exact keys:

```text
exact_identity, dataset_verified, version_lifecycle_verified,
row_schema_verified, ledger_match_parity, match_episode_parity,
cost_rebuilt, summary_rebuilt, no_incomplete_matches, no_duplicates,
no_external_calls, all_conditions_accepted
```

Manifest schema literals are `r6-ledger-manifest-v1`,
`r6-match-manifest-v1`, `r6-result-manifest-v1`, and
`r6-postflight-v1`. Postflight verdict is exactly `ACCEPTED` or `REJECTED`.
`all_conditions_accepted` must equal logical AND of the other eleven booleans;
`ACCEPTED` is legal only when it is true.

The four runtime evidence inputs `source_eof_verified`, `dataset_verified`,
`version_lifecycle_verified`, and `no_external_calls` must be exact JSON/Python
booleans before postflight construction. Strings, integers, Decimal values,
and every other truthy/falsy alias fail closed; construction never applies a
truthiness conversion.

No artifact row, manifest, postflight, release body, or artifact digest contains
`created_at`, `updated_at`, actor, change note, retry start/end time, or any
other wall-clock/audit field. Those values are saved in PostgreSQL operation and
attempt-generation audit columns only. Rebuilding the same canonical evidence
under a different clock must produce byte-identical artifacts and identical
roots. Injecting any audit field into an exact artifact schema fails closed.

Adjacent multiplicity tokens are exactly `(sequence, signal_id, semantic_key)`.
Ledger ↔ match ↔ episode parity must be bidirectional with `EXCEPT ALL`
semantics and zero duplicate count. Same-count substitution is a failure.

### 6.5 Family release projection and public bundle

Individual G4 result manifests, episode chunks, summaries, and postflights are
quarantined PostgreSQL evidence until all seven attempts are `ACCEPTED`; they
are not filesystem artifacts and have no public locator. After the 7/7 barrier,
the release use case creates one exact `family_release` body with keys:

```text
schema_version, family_id, matrix_id, registration_digest,
research_baseline_digest, protocol_core_digest, family_head_sequence,
ordered_accepted_attempts
```

`schema_version=r6-family-release-v1` and `family_head_sequence=7`.
`ordered_accepted_attempts` has exactly seven rows ordered by slot; each row has
exact keys `slot_sequence`, `attempt_id`, `attempt_revision`,
`accepted_retry_generation`, `hypothesis_id`, `result_manifest_digest`,
`result_projection_digest`, and `postflight_digest`. `family_release_digest` is
the digest of this body.

Only after the transaction has verified and sealed that release body may a
materializer read quarantine evidence and build the public family bundle. The
public bundle manifest exact keys are:

```text
schema_version, family_id, matrix_id, registration_digest,
family_release_digest, payload_contract_version, episode_chunk_row_limit,
ordered_slot_payloads, bundle_member_count, bundle_content_byte_count,
bundle_payload_sha256, bundle_manifest_digest
```

Literals are `schema_version=r6-public-family-bundle-v1`,
`payload_contract_version=r6-public-family-bundle-payload-v1`, and
`episode_chunk_row_limit=10000`. `ordered_slot_payloads` contains exactly seven
rows ordered by `slot_sequence=1..7`. Each slot row has the exact keys:

```text
slot_sequence, hypothesis_id, result_manifest_path, result_manifest_digest,
result_manifest_byte_count, result_manifest_file_sha256, postflight_path,
postflight_digest, postflight_byte_count, postflight_file_sha256,
episode_count, episode_rows_sha256, episode_chunks
```

Paths are exact lowercase POSIX relative paths with no leading slash,
backslash, empty segment, `.`/`..`, percent encoding, Unicode alias, or symlink:

```text
slots/01/result_manifest.json
slots/01/postflight.json
slots/01/episodes/00000001.jsonl
...
slots/07/result_manifest.json
slots/07/postflight.json
slots/07/episodes/00000001.jsonl
```

The slot component is zero-padded decimal width 2. Episode chunk names are
one-based, zero-padded decimal width 8. `result_manifest.json` and
`postflight.json` are their exact canonical JSON object plus one terminal LF;
their `*_file_sha256` fields hash those complete bytes, including the LF.

Episode rows retain ascending `sequence` and their already-verified canonical
JSONL bytes; the materializer must not parse/re-serialize them. Chunk `k`
contains episode sequences `((k-1)*10000)+1` through
`min(k*10000, episode_count)`. Every non-final chunk has exactly 10,000 rows;
the final chunk has 1-10,000 rows. `episode_count=0` has an empty
`episode_chunks` array and no episode file. Otherwise chunk count is exactly
`ceil(episode_count/10000)`. Each `episode_chunks` row has exact keys:

```text
chunk_sequence, path, row_start_sequence, row_end_sequence, row_count,
byte_count, sha256
```

`chunk_sequence`, row positions, counts, and byte counts are JSON integers.
`sha256` hashes the exact complete chunk bytes. Concatenating all chunk content
bytes in chunk order must reproduce `episode_rows_sha256`; for zero episodes it
is SHA-256 of the empty byte string.

The payload member order is exact: slot 1 through 7; within each slot,
`result_manifest.json`, then `postflight.json`, then episode chunks by
`chunk_sequence`. There are no other payload members. Therefore
`bundle_member_count = 14 + sum(episode_chunk_count)` and
`bundle_content_byte_count` is the sum of all member content-byte lengths.
Both fields count payload members/content only and exclude
`bundle_manifest.json` plus path/length framing bytes.

For each ordered member, let `P` be its exact UTF-8 relative-path bytes and `C`
its exact content bytes. Its frame is:

```text
uint32_be(len(P)) || P || uint64_be(len(C)) || C
```

`uint32_be` and `uint64_be` are unsigned fixed-width big-endian integers;
there is no separator, newline, archive header, compression, or filesystem
metadata in the frame. `bundle_payload_sha256` is SHA-256 over the concatenation
of every member frame in the declared order. `bundle_manifest.json` is not a
payload member; it is the exact completed manifest object plus LF at the bundle
root. The public directory contains only `bundle_manifest.json` and the declared
payload paths. File mode, directory mode, owner, inode, and mtime are operation
metadata and never identity.

The normative framing-only golden vector uses
`P=slots/01/result_manifest.json` and `C={}\n` (the content is not a valid R6
manifest; it tests framing only):

```text
len(P) = 29
len(C) = 3
frame_hex = 0000001d736c6f74732f30312f726573756c745f6d616e69666573742e6a736f6e00000000000000037b7d0a
sha256(frame) = 5401347ec77cbd9bd93b1a82a3f181b4c507246e789e34b697ed12f87dd7da2b
```

The bundle contains all seven results or none. It has no individual pre-release
public path and no audit timestamp. The materializer rebuilds every descriptor,
member count, byte count, file/chunk SHA, concatenated episode SHA, framed
payload SHA, and manifest digest before atomic rename. The public artifact
catalog is written only while the family release row remains unchanged.
Response-loss or clean-root reconstruction reads the immutable quarantine bytes
and saved release body, uses the same boundaries/order/framing, and must produce
the same relative paths, file bytes, `bundle_payload_sha256`, and manifest
digest.

Verification is semantic as well as byte-level. A caller must supply the sealed
`family_release`; the verifier parses every manifest and postflight as exact
canonical JSON, parses every episode JSONL row without blank/non-canonical
bytes, invokes the layer verifiers, rebuilds row lineage, multiplicity,
summary, counts, and episode payload SHA, and compares every result/postflight
root with the ordered accepted-attempt roots in the release. Recomputing only
member/file/framing hashes after changing inner content can never make a bundle
valid.

Chunk verification is physical, not descriptor-only. For every declared chunk,
the verifier counts the parsed JSONL rows and requires that count to equal
`row_count`; the first and last physical row sequences must equal
`row_start_sequence` and `row_end_sequence`. Every non-final physical chunk
must contain exactly 10,000 rows. Concatenated global sequence continuity does
not excuse a different physical partition such as `9,999 / 2`.

## 7. Frozen evaluation contract

### 7.1 Research window

All seven slots use the full manifest date range for the primary exploratory
screen. There is no train/validation optimization and no OOS claim because all
parameters were selected after historical data existed.

For stability, use only complete calendar quarters entirely inside the Dataset:

```text
2023Q4, 2024Q1, 2024Q2, 2024Q3, 2024Q4,
2025Q1, 2025Q2, 2025Q3, 2025Q4, 2026Q1, 2026Q2
```

Partial 2023Q3 and 2026Q3 remain in full-period metrics but not in the
quarter-stability denominator. Date assignment uses `exit_session_date`.

### 7.2 Exact metrics

Every slot saves the same metrics:

- signal, match, episode, win, loss, tie, and independent exit-day counts;
- sum/mean/median pre-slippage return;
- sum/mean/median net return on raw entry notional;
- one-lot pre-slippage P&L, post-slippage gross P&L, explicit costs, and net P&L;
- return-based Profit Factor: sum positive episode net returns divided by the
  absolute sum of negative episode net returns;
- one-lot P&L Profit Factor as a secondary descriptive metric;
- daily equal-signal return: arithmetic mean episode net return for each exit
  date;
- daily equal-signal compounded curve and maximum drawdown;
- mean net return and episode count for each of the eleven complete quarters;
- deterministic daily-cluster bootstrap lower bound.

Summary exact keys:

```text
schema_version, episode_count, independent_exit_day_count,
win_count, loss_count, tie_count, sum_pre_slippage_return,
mean_pre_slippage_return, median_pre_slippage_return, sum_net_return,
mean_net_return, median_net_return, sum_pre_slippage_price_pnl,
sum_post_slippage_gross_pnl, sum_explicit_costs, sum_net_pnl,
return_profit_factor, pnl_profit_factor, daily_equal_signal_max_drawdown,
complete_quarter_count, positive_complete_quarter_count,
positive_complete_quarter_ratio, quarter_metrics, bootstrap,
disposition, limitations
```

Literal `schema_version=r6-result-summary-v1`.
`return_profit_factor` and `pnl_profit_factor` are exact objects with keys
`status` and `value`; status is `FINITE`, `POSITIVE_INFINITY`, or `UNDEFINED`,
and value is a canonical Decimal string only for `FINITE`.
Each `quarter_metrics` row has exact keys `quarter`, `episode_count`, and
`mean_net_return`, ordered chronologically. `limitations` is the ordered exact
array containing `EXPLORATORY_ONLY_NO_PROMOTION` plus Dataset manifest issues in
their saved order.

Return sums use Decimal precision 38 over unquantized episode values. Mean and
median returns, daily returns, drawdown, quarter means/ratio, and bootstrap
estimates are quantized to 18 decimal places with `ROUND_HALF_EVEN`. Median is
the middle sorted value for odd count and the mean of the two middle values for
even count. `win/loss/tie` compare exact `net_pnl` with zero.

Daily equal-signal drawdown starts with wealth and peak `1`. For each exit date
in ascending order, daily return is the arithmetic mean of that date's episode
net returns. That daily return is first quantized to 18 decimal places with
`ROUND_HALF_EVEN`; only the quantized value may be used in
`wealth = wealth * (1 + daily_return)`. Peak is then updated and drawdown is
`(peak - wealth) / peak`. Non-positive wealth, non-finite Decimal, or division
failure rejects the result rather than clamping it.

After the curve is complete, maximum drawdown is quantized exactly once to the
same canonical 18-decimal `ROUND_HALF_EVEN` value. Both the `<= 0.20`
disposition comparison and `daily_equal_signal_max_drawdown` serialization use
that one value; the unquantized intermediate is never compared independently.

FINITE Profit Factor uses Decimal precision 38, division quantized to 18
decimal places with `ROUND_HALF_EVEN`, then canonical Decimal normalization.
Zero loss with positive gains is `POSITIVE_INFINITY`; zero gain and zero loss
is `UNDEFINED`; neither special state silently passes a finite comparison.

### 7.3 Multiple-testing and bootstrap

The server-owned family policy remains:

```text
planned_attempts = 20
family_alpha = 0.05
adjustment_method = BONFERRONI
adjusted_one_sided_alpha = 0.0025
registered_slots = 1..7
slots 8..20 = UNAVAILABLE
```

Bootstrap contract:

1. cluster unit is complete `exit_session_date`;
2. resample complete date clusters with replacement;
3. statistic is mean episode net return across all episodes in sampled clusters;
4. use exactly `20,000` samples;
5. sampling is implementation-neutral: for sample index `b` and draw index
   `d`, compute `sha256(seed_utf8 || uint64_be(b) || uint32_be(d))`, interpret
   the first eight bytes as unsigned big-endian, and take modulo the number of
   independent dates; `seed_utf8` is exact ASCII
   `family_id + ':' + hypothesis_id + ':bootstrap-v1'`;
6. sort the 20,000 estimates ascending;
7. the one-sided lower bound is zero-based index
   `ceil(0.0025 * 20000) - 1 = 49`;
8. fewer than 20 independent dates is `INSUFFICIENT_EVIDENCE`.

When a date is drawn more than once, its complete episode cluster is included
the same number of times. Each bootstrap statistic is quantized to 18 decimal
places after the pooled mean is calculated. The exact `bootstrap` summary keys
are `schema_version`, `cluster_unit`, `sample_count`, `adjusted_alpha`,
`independent_date_count`, `seed_digest`, and `lower_bound`; schema literal is
`r6-daily-cluster-bootstrap-v1`.

### 7.4 Disposition matrix

Integrity failure never yields metrics. After integrity acceptance:

`PASS_EXPLORATORY_SCREEN` requires all of:

```text
episodes >= 30
independent exit dates >= 20
mean pre-slippage return > 0
mean net return > 0
return-based Profit Factor > 1
daily-cluster bootstrap lower bound > 0 at alpha 0.0025
positive complete-quarter ratio >= 7 / 11
daily equal-signal maximum drawdown <= 0.20
```

If evidence floors are missing, disposition is `INSUFFICIENT_EVIDENCE`. If
floors and integrity pass but any economic/statistical/stability threshold
fails, disposition is `RESEARCH_REJECT`. Dataset
`research_eligible=false` adds the immutable limitation
`EXPLORATORY_ONLY_NO_PROMOTION` to every disposition.

The report may sort candidates descriptively by disposition class, bootstrap
lower bound, mean net return, return-based Profit Factor, and slot sequence.
It must not call the first row a statistically unique winner. Pairwise tests
would be 21 additional hypotheses and require a new pre-registered family.

A complete quarter with zero episodes makes the slot
`INSUFFICIENT_EVIDENCE`; it is not silently counted as a negative quarter.
`POSITIVE_INFINITY` return-based Profit Factor passes the PF guard only when
positive return sum is greater than zero and negative return sum is exactly
zero. `UNDEFINED` Profit Factor never passes.

## 8. Family, matrix, and attempt persistence

Existing `backtest_experiment_attempts` requires a normal Backtest `run_id` and
cannot truthfully represent independent Replay attempts. R6 must not create
fake Runs or weaken that foreign key. Migration 016 candidate therefore adds a
dedicated PostgreSQL-only R6 ledger while reusing the approved policy values.

Required durable tables:

1. `atomic_entry_benchmark_families`: stable family identity, source lineage
   Run, exact research baseline body/digest, exact protocol-core body/digest,
   planned attempts 20, alpha 0.05, BONFERRONI, head sequence, release state,
   actor, and created time. Unique research baseline digest prevents an
   equivalent family from resetting the budget. Audit time is not identity.
2. `atomic_entry_benchmark_matrices`: immutable revision-1 registration body,
   registration digest, seven registered slots, status `SEALED`, actor/change
   note/sealed time. Only one revision may be active for the research baseline.
3. `atomic_entry_benchmark_slots`: exact hypothesis specification, Version
   binding, hypothesis ID, ordered slot projection, and slot digest. Rows are
   immutable; mutable execution state lives in attempt rows.
4. `atomic_entry_benchmark_attempts`: monotonic sequence, slot, immutable
   attempt ID/request digest, status, attempt revision, retry generation,
   progress, preflight/replay IDs, quarantined result/postflight roots, failure
   code, and terminal time. Unique family/sequence, family/slot, attempt ID,
   replay ID, and operation scope. Retry never inserts another attempt row.
5. `atomic_entry_benchmark_operations`: durable idempotency key, request digest,
   immutable result body/digest, actor, operation type, and created time.
6. `atomic_entry_benchmark_transition_evidence`: append-only transition CAS
   projection keyed by operation ID and attempt revision. It independently
   preserves from/result progress, requested progress, statuses, generations,
   outcome, and the canonical request/result digests in the same transaction.
7. `atomic_entry_benchmark_outbox`: inserted in the same transaction as every
   family/matrix/attempt terminal mutation; notification is not authoritative.
8. `atomic_entry_benchmark_result_chunks`: PostgreSQL-only canonical episode
   chunks, manifests, summaries, and postflights keyed by attempt plus retry
   generation. Infrastructure methods may write/revalidate them, but no public
   repository or artifact-catalog method can resolve them before family release.
9. `atomic_entry_benchmark_releases`: immutable family-release body/digest,
   ordered accepted roots, state, public-bundle digest/locator after publication,
   and operation audit. There is exactly one release per matrix revision.

`research_baseline_digest`, `protocol_core_digest`, hypothesis specifications,
Version bindings, slots, matrix, and registration use the exact projections and
dependency order in Section 3.5. A new implementation therefore resolves the
existing family/head and still requires a reviewed matrix revision; it never
creates a fresh attempt budget.

All mutations use PostgreSQL row locks and transaction-per-checkout. SQLite,
missing PostgreSQL, or schema mismatch fails closed. No fallback is allowed.

## 9. Mutation and visibility contract

### 9.1 Matrix seal

One transaction locks/creates the stable family head, verifies head `0`,
verifies all seven Versions and lifecycle projections, inserts matrix and all
slots, and saves operation result plus outbox. Same key/digest replays the
original result. Same key/different digest conflicts. A second matrix for the
same revision conflicts.

Version verification is the complete G1 durable publication graph, not a
configuration-only shortcut. It rebuilds the current and stored Template roots,
canonical Version configuration, sealed Draft body/revision, canonical publish
request, event/evidence/projection, publish operation result, and lifecycle
outbox. Slots 1, 3, 4, and 5 additionally require the frozen G1 actor, actor
session, change note, and inception revision. A self-consistent rewrite of the
publication graph under a different actor still fails closed.

### 9.2 G3 preflight

G3 scans the Dataset once and builds all seven ledgers/match plans before any
performance result exists. Publication is all-or-none: each slot must pass
Dataset-to-ledger and ledger-to-match audit, and all seven manifests are sealed
in one operation. G3 does not advance the formal attempt head.

### 9.3 G4 formal attempts

Attempts are consumed strictly in slot order 1-7 under the family-head lock.
The attempt sequence equals slot sequence. An attempt is consumed before result
calculation and cannot be removed, renumbered, or replaced. The exact statuses
and legal transitions are:

| From | To | Current generation guard | Exact outcome-code guard | Meaning |
|---|---|---:|---|---|
| none | `RUNNING` | absent | `ATTEMPT_STARTED` | consume next slot; create revision 1 and generation 1 |
| `RUNNING` | `CANCELLING` | `1..4` | `OPERATOR_CANCELLED` | accept cancellation and preserve progress |
| `CANCELLING` | `CANCELLED_RETRYABLE` | `1..3` | `OPERATOR_CANCELLED` | flush progress and close a retryable cancelled generation |
| `CANCELLING` | `CANCELLED_FINAL` | `4` | `OPERATOR_CANCELLED` | flush progress and exhaust cancellation recovery |
| `RUNNING` | `FAILED_RETRYABLE` | `1..3` | one retryable infrastructure code | close a retryable technical failure |
| `RUNNING` | `FAILED_FINAL` | `4` | one retryable infrastructure code | close an infrastructure failure at the retry ceiling |
| `RUNNING` | `FAILED_FINAL` | `1..4` | `UNCLASSIFIED_FAILURE` | fail closed on an unmapped exception |
| `RUNNING` | `REJECTED_FINAL` | `1..4` | one integrity-rejection code | reject identity/evidence/postflight integrity |
| `RUNNING` | `ACCEPTED` | `1..4` | `POSTFLIGHT_ACCEPTED` | accept result/postflight into quarantine |
| `FAILED_RETRYABLE` | `RUNNING` | `1..3` | `ATTEMPT_RETRY_STARTED` | CAS retry same attempt at generation + 1 |
| `CANCELLED_RETRYABLE` | `RUNNING` | `1..3` | `ATTEMPT_RETRY_STARTED` | CAS retry same attempt at generation + 1 |
| `FAILED_RETRYABLE` | `FAILED_FINAL` | `1..3` | `OPERATOR_SEALED_TECHNICAL_FAILURE` | permanently seal a retryable technical failure |
| `CANCELLED_RETRYABLE` | `CANCELLED_FINAL` | `1..3` | `OPERATOR_SEALED_CANCELLATION` | permanently seal a retryable cancellation |

All unspecified transitions fail closed. `ACCEPTED`, `REJECTED_FINAL`,
`FAILED_FINAL`, and `CANCELLED_FINAL` are terminal. A final non-accepted status
permanently prevents family release; it cannot be hidden by a new family,
matrix, slot, or attempt.

Every status transition uses `WHERE attempt_revision = expected_revision AND
status = expected_status` and increments `attempt_revision` by exactly one.
Progress-only writes do not change the revision; they update with an atomic
monotonic maximum and terminal transitions preserve/flush the greatest durable
value. A zero-row CAS reloads the operation mapping first for response-loss
replay, then returns a revision/status conflict if no matching result exists.

The exact retryable infrastructure-code set is
`WORKER_PROCESS_INTERRUPTED`, `POSTGRES_TRANSIENT_UNAVAILABLE`,
and `TEMP_STORAGE_UNAVAILABLE`. The exact integrity-rejection-code set is
`DATASET_IDENTITY_REJECTED`, `VERSION_IDENTITY_REJECTED`,
`FEATURE_IDENTITY_REJECTED`, `CANONICAL_BYTES_REJECTED`, `PARITY_REJECTED`,
`COST_IDENTITY_REJECTED`, `SUMMARY_REBUILD_REJECTED`, and
`POSTFLIGHT_REJECTED`. `OPERATOR_CANCELLED` is a cancellation outcome, never an
infrastructure failure. Every error/outcome code maps to exactly the transition
rows above; requests cannot choose or reclassify a code. Any exception that
cannot be deterministically mapped uses `UNCLASSIFIED_FAILURE` and terminates
`FAILED_FINAL` at every generation. An integrity code always terminates
`REJECTED_FINAL`. A retryable infrastructure code terminates
`FAILED_RETRYABLE` only in generations 1-3 and `FAILED_FINAL` in generation 4.
`OPERATOR_CANCELLED` terminates `CANCELLED_RETRYABLE` only in generations 1-3
and `CANCELLED_FINAL` in generation 4.

The application exposes explicit request-cancellation, complete-cancellation,
retry, seal-retryable, and record-worker-failure use cases. It does not expose
an application command that accepts arbitrary `next_status` plus `outcome_code`.
Worker failures are classified by an exact server-owned exception-type map;
unknown exceptions become `UNCLASSIFIED_FAILURE`, never a retryable alias.

The server-owned retry ceiling is three retries after the initial generation:
`retry_generation` is an exact JSON/PostgreSQL integer in `1..4`. A retry
request has exact scope `(family_id, matrix_id, attempt_id, expected_revision,
prior_status, next_retry_generation)`, requires a fresh idempotency key and
request digest, and locks the family plus attempt row. It increments
`attempt_revision` and `retry_generation` atomically but preserves family ID,
matrix, slot, attempt ID, attempt sequence, hypothesis, input digests, and
family head. It never increments planned-attempt consumption or creates a new
hypothesis opportunity. Same key/digest replays the saved transition; stale
revision, different digest, changed inputs, or retry beyond generation 4
conflicts. Prior generation audit and partial chunks remain immutable technical
evidence and are never eligible for performance publication.

An accepted attempt writes result chunks, result manifest, summary, and
postflight only to the PostgreSQL quarantine tables in the same transaction as
the `ACCEPTED` CAS. No filesystem result artifact, public catalog record,
download locator, report row, comparison row, or performance event is created
per slot. The seventh accepted attempt may only make the family
`READY_TO_RELEASE`; Section 9.5 performs the separate all-seven release.

### 9.4 Cancellation and response loss

- Cancellation uses status CAS, preserves current progress, and converges
  `RUNNING -> CANCELLING -> CANCELLED_RETRYABLE` for an unexhausted attempt.
- Worker terminalization cannot overwrite `CANCELLING`.
- Every terminal path flushes pending progress.
- Same-key response-loss replay reads immutable operation result without
  consulting current Template/Registry/artifact locators.
- Transition replay rebuilds the exact status, revision, retry generation, and
  outcome from the original canonical request. Its progress is rebuilt from the
  independently persisted transition CAS evidence, never from the result being
  verified. The complete saved result must equal both that evidence and the
  transactionally inserted operation outbox. Synchronized result/outbox
  substitution therefore cannot change historical progress or classification.
- Different digest under the same key returns conflict.
- Artifact paths are locators/audit only and never enter semantic identity.

### 9.5 Family quarantine, unified reader, and release

Before all seven attempts are `ACCEPTED`, the only safe product projection is:

```text
schema_version, family_id, matrix_id, slot_sequence, attempt_id, status,
attempt_revision, retry_generation, progress, integrity_status,
integrity_diagnostic_codes
```

`schema_version=r6-redacted-attempt-status-v1`. It contains no episode row,
price, P&L, return, Profit Factor, drawdown, summary, disposition, rank,
result/postflight digest, filesystem/database locator, or payload excerpt.
Diagnostic codes identify contract checks only and cannot contain observed
values.

The exact diagnostic-code allowlist is:

```text
DATASET_IDENTITY_VERIFIED, VERSION_IDENTITY_VERIFIED,
FEATURE_IDENTITY_VERIFIED, CANONICAL_BYTES_VERIFIED, PARITY_VERIFIED,
COST_IDENTITY_VERIFIED, SUMMARY_REBUILD_VERIFIED, POSTFLIGHT_VERIFIED,
DATASET_IDENTITY_REJECTED, VERSION_IDENTITY_REJECTED,
FEATURE_IDENTITY_REJECTED, CANONICAL_BYTES_REJECTED, PARITY_REJECTED,
COST_IDENTITY_REJECTED, SUMMARY_REBUILD_REJECTED, POSTFLIGHT_REJECTED
```

PostgreSQL rejects non-array, non-string, duplicate, or non-allowlisted codes
on write. The unified reader independently applies the same checks on read so a
damaged database row cannot turn into a pre-release value channel.

`BenchmarkResultReader` is the single application port for result, comparison,
export, report, disposition, audit-result, CLI-show, and artifact-download
paths. It first locks or snapshot-reads the family release row and returns only
the redacted projection unless `release_state=RELEASED`, the stored public
bundle root verifies, and all seven accepted roots still match the immutable
release body. FastAPI handlers, dashboard code, CLI commands, report builders,
artifact stores, outbox consumers, and tests may not call quarantine repository
read methods directly. Quarantine read methods are private infrastructure
methods callable only by postflight, formal SQL, and release use cases.
Formal SQL can open quarantine evidence only after its initial repeatable-read
snapshot proves family head `7` and all seven attempts `ACCEPTED`; otherwise it
raises before selecting any result/summary column.

Workers and CLIs print only redacted projection fields. Logs and exceptions use
stable error codes plus family/attempt IDs; they must not serialize result
objects, summaries, locators, SQL rows, or traceback local values. Outbox events
before release contain status/integrity codes only. No product filesystem
result artifact is created before seven `ACCEPTED` statuses exist. Direct
PostgreSQL administrator access is outside the single-user trusted-database MVP
threat model, but no application repository/API/CLI path exposes quarantine
payloads.

Release requires one idempotent operation with expected matrix digest, family
head `7`, and the seven expected attempt revisions/result/postflight roots. In
one PostgreSQL transaction it locks the family, revalidates all identities and
quarantine chunks, verifies seven `ACCEPTED` attempts, creates the immutable
Section 6.5 release body, and sets `release_state=MATERIALIZING`. Only then can
the materializer build a plaintext filesystem bundle; therefore no plaintext
result artifact exists before the 7/7 condition is true. The bundle is built in
a private temp directory, fully verified, and atomically renamed. A final
transaction revalidates the release digest and bundle bytes, inserts the public
catalog/outbox rows, and sets `RELEASED`. Until that final commit, the unified
reader remains redacted. Crash after either transaction is safely replayed from
the immutable release body; it cannot produce a partially visible family.

## 10. Acceptance and adversarial tests

Gates must cover at least:

- all seven Version/parameter/schema/implementation/Feature identities;
- published Bollinger 10 versus default 20 drift;
- missing or non-PUBLISHED Version;
- Feature state isolation across slot, request, symbol, and session;
- first-trigger-only parity with current Backtest engine;
- strategy-specific golden signals and missing-data fail-closed behavior;
- source raw bytes versus parsed bar values;
- full Dataset line count/SHA/EOF verification;
- cross-session entry rejection, missing entry/exit, duplicates, substitution,
  and all adjacent-layer `EXCEPT ALL` parity;
- canonical bytes, exact schema, unknown fields, numeric aliases, Decimal and
  timestamp formatting;
- cost math and R5 cost-identity parity;
- server-owned alpha/attempt policy and slots 8-20 rejection;
- equivalent-family budget reset attempt;
- golden reconstruction of every exact identity stage, proof that G0 specs do
  not require Version IDs, and proof that no downstream digest feeds upstream;
- same-key replay, different-digest conflict, concurrent matrix seal, strict
  slot order, concurrent slot consumption, cancellation races, and progress
  terminal flush;
- same-attempt retry CAS, exact retry-generation ceiling, concurrent retry,
  stale revision, response loss, immutable input drift, no new sequence/head,
  and retryable-versus-final failure-code regressions;
- generation-4 infrastructure failure and cancellation must exercise the exact
  direct `FAILED_FINAL`/`CANCELLED_FINAL` rows; wrong generation, error-code
  substitution, or any unlisted transition must fail closed;
- self-consistent manifest/result/postflight tamper;
- identical semantic artifact bytes/digests under different injected clocks and
  rejection of audit timestamp fields in artifacts;
- result redaction until all seven accepted across repository, API, dashboard,
  CLI, filesystem catalog, report, export, outbox, log, and exception paths;
- zero pre-release filesystem result artifacts, private quarantine access,
  all-seven release, response-loss bundle rebuild, materialization crash before
  catalog commit, bundle tamper, and unified-reader fail-closed regressions;
- public-bundle golden bytes for zero, one, exactly 10,000, and 10,001 episode
  boundaries; path/order/chunk/row substitution, missing/extra member, newline,
  frame-length, member-count, byte-count, chunk SHA, episode SHA, payload SHA,
  and clean-root/response-loss byte-parity regressions;
- bootstrap seed/sample/quantile golden vector and quarter-boundary tests;
- zero provider, broker, CA, trade subscription, Local Paper, or lifecycle
  mutation calls.

Formal SQL runs in one `REPEATABLE READ READ ONLY` transaction, accepts caller-
supplied expected matrix/result/postflight digests, recomputes all counts,
adjacent multiplicity projections, cost identities, summary metrics, and
dispositions, then raises a SQL error after rollback when any assertion fails.

## 11. Implementation slices

| Gate | Scope | Exit condition | Current status |
|---|---|---|---|
| G0 | Contract and exact hypothesis admission | Independent Review closes all contract blockers | PASSED / A1 CONTRACT FROZEN |
| G1 | Publish four missing Versions; pure domain/artifacts | Exact Version verification plus golden/bounded tests | PASSED |
| G2 | PostgreSQL family/matrix/application | Migration, idempotency, concurrency, tamper, redaction tests | PASSED |
| G3 | Full-Dataset seven-ledger preflight | 28.3M bars, seven sealed audited ledgers/matches, no metrics | BLOCKED ON A1 IMPLEMENTATION |
| G4 | Seven formal one-lot replays | Seven accepted attempts and formal SQL | BLOCKED ON G3 |
| G5 | Comparative disposition | Frozen matrix applied, report sealed, no lifecycle mutation | BLOCKED ON G4 |

Each Gate requires independent approval. G1 approval only removes G2's
prerequisite blocker; it does not authorize G2 implementation, full-Dataset
preflight, or formal replay. G5 completion does not authorize Local Paper.

## 12. Proposed file map

```text
architecture/r6_atomic_entry_benchmark_v2_implementation_plan.md
backtest/atomic_benchmark/domain.py
backtest/atomic_benchmark/artifacts.py
backtest/atomic_benchmark/preflight.py
backtest/atomic_benchmark/__init__.py
backtest/atomic_benchmark/repository.py
backtest/atomic_benchmark/postgres_repository.py
backtest/atomic_benchmark/application.py
backtest/atomic_benchmark/result_reader.py
backtest/migrations/016_atomic_entry_benchmark.sql
backtest/migrations/017_r6_matrix_revision_and_preflight.sql
scripts/publish_r6_g1_strategy_versions.py
scripts/preflight_atomic_entry_benchmark.py
scripts/execute_atomic_entry_benchmark.py
scripts/audit_atomic_entry_benchmark.py
.planning/2026-08-26-r6-atomic-strategy-benchmark/
tests/test_atomic_entry_benchmark_domain.py
tests/test_atomic_entry_benchmark_artifacts.py
tests/test_r6_g1_version_publication.py
tests/test_atomic_entry_benchmark_application.py
tests/test_atomic_entry_benchmark_postgres.py
tests/test_atomic_entry_benchmark_full_dataset.py
tests/test_atomic_entry_benchmark_preflight_postgres.py
```

Dependency direction is fixed:

```text
domain.py <- repository.py ports <- application.py use cases
domain.py <- artifacts.py adapter
repository.py ports <- postgres_repository.py adapter
application.py <- CLI composition roots
```

`domain.py` contains framework-free value objects, signal/match/economic math,
identity construction, and disposition rules; it cannot import psycopg,
FastAPI, CLI, or filesystem locators. `repository.py` defines ports only.
`postgres_repository.py` owns SQL/transactions and maps rows to domain values.
G3 non-performance artifacts use a filesystem adapter behind an explicit
catalog/store port. G4 performance evidence remains in private PostgreSQL
quarantine until family release; only the family bundle is then materialized
through the public artifact adapter. Every product result read uses
`result_reader.py`.
CLI modules parse inputs, build dependencies, call one application use case,
and format output; no research rule or SQL lives in a CLI handler. Pure domain
and application tests use in-memory ports without Docker or network.

Migration number `016` was rechecked immediately before implementation and is
owned by the forward-only runner. G2 adds the complete PostgreSQL schema,
matrix/application ports, transaction-per-checkout adapter, durable operation
and outbox writes, exact attempt state machine, and unified pre-release reader.

## 13. G0 decision

```text
R6 revision 2 design: G0 APPROVED / CONTRACT FROZEN
G0 Amendment A1: PASSED / CONTRACT FROZEN
G1 Version publication / pure domain-artifact implementation: PASSED
G2 PostgreSQL family/matrix mutation: PASSED
G3 full-Dataset preflight: BLOCKED ON A1 IMPLEMENTATION
Formal replay / result inspection: NOT AUTHORIZED
Local Paper / Broker / Real-money: PROHIBITED
```

## 14. G0 Amendment A1: common cutoff and incomplete-signal contract

### 14.1 Reason and authority boundary

The revision-1 G3 preflight failed before publication because slot 1 signal
sequence `101` had a later entry Kbar but no still-later same-session exit Kbar.
All seven sealed Strategy Versions already use an exclusive
`entry_window_end <= 12:45`; ORB ends at `11:00`. The failure is therefore a
Dataset coverage boundary, not authority to move the strategy cutoff to
`13:28`, drop only the losing slot's signal, invent a close, or carry overnight.

Amendment A1 makes Dataset coverage eligibility common and strategy-agnostic.
It uses only the existence and timestamps of canonical source Kbars, never
OHLCV values, Feature values, signals, prices after entry, returns, or P&L. The
same eligible `(symbol, session_date)` set is applied to all seven slots before
any first-trigger admission. The revision-1 matrix remains immutable and has
head `0`, attempts `0`; it is not executable after this amendment.

This section is the approved and frozen A1 contract. Approval does not
authorize product code, Migration 017, matrix revision 2, another full-Dataset
G3 run, G4, lifecycle, Local Paper, provider, broker, or real-money work.

### 14.2 Exact time and eligibility semantics

All times are exact `Asia/Taipei` completed one-minute Kbar labels:

```text
common_signal_cutoff_time = 12:45
common_signal_cutoff_comparator = STRICT_LT
entry_fill_deadline_time = 12:45
entry_fill_deadline_comparator = LTE
required_terminal_exit_time = 13:30
```

Each Version must satisfy `entry_window_end <= 12:45`; a later value fails
matrix admission. Existing strategy evaluation remains start-inclusive and
end-exclusive, so a Kbar labelled exactly `12:45` cannot create a signal.

A `(symbol, session_date)` is `ELIGIBLE` only when its canonical Dataset rows
contain exactly one completed Kbar at `12:45` and exactly one at `13:30`.
Duplicate anchor timestamps are Dataset corruption and fail the whole G3
operation. Missing anchors produce a common `EXCLUDED` row, not a strategy
signal or match:

```text
MISSING_ENTRY_RESERVE_12_45
MISSING_TERMINAL_EXIT_13_30
```

Reason codes use the order above; both may be present. Exact `12:45` guarantees
that any admitted signal before the cutoff has a next observed entry no later
than `12:45`. Exact `13:30` is the terminal exit and must be strictly later than
entry. Cross-session entry/exit, same-bar entry/exit, a last-observed partial
session close, overnight carry, and synthetic bars remain prohibited.

The Dataset is read once. One session is spooled in bounded temporary storage;
at the session boundary the common eligibility mask is determined, then that
same canonical session stream is evaluated by all seven isolated runtimes.
The spool is a locator, never identity, and is deleted after the session.

Source traversal and strategy admission are distinct. Every canonical row,
including rows from an excluded symbol/session, still participates in Dataset
count/SHA/EOF/order verification and in the source-only `previous_close` map.
For a symbol, `previous_close` is the final observed close from its immediately
preceding observed Dataset session whether or not that preceding session was
eligible. An excluded symbol/session is never passed to a strategy or Feature
runtime, creates no evaluation/ledger/match row, and cannot mutate a slot's
Feature state. For each Dataset date, each isolated runtime receives exactly one
`begin_session(session_date)` before the first eligible symbol/bar on that date;
if the date has no eligible symbol/session, no runtime session is opened. An
eligible symbol/session is replayed from its first canonical bar so session open,
high, VWAP, volume, and rolling Feature state use the complete observed prefix.

The coverage ratio is computed before strategy evaluation:

```text
observed_symbol_session_count = distinct Dataset (symbol, session_date) count
eligible_symbol_session_count = rows with both exact anchors
eligible_symbol_session_ratio = eligible / observed
eligibility_ratio_scale = 18
eligibility_ratio_rounding = ROUND_HALF_EVEN
minimum_eligible_symbol_session_ratio = 0.95
eligibility_ratio_comparator = GTE
```

Zero observed rows or a canonical ratio below `0.950000000000000000` rejects
G3 without artifact publication. The G5 report must display all coverage
counts and state that results apply only to the common coverage-qualified
universe; this Dataset remains exploratory and cannot support promotion.

### 14.3 Exact eligibility artifacts

Eligibility rows are ordered by `(session_date, symbol)` ascending and have
the exact keys:

```text
schema_version, sequence, symbol, session_date,
entry_reserve_at, entry_reserve_bar_digest,
terminal_exit_at, terminal_exit_bar_digest,
eligibility_status, exclusion_reason_codes, eligibility_row_digest
```

`schema_version=r6-session-eligibility-row-v1`; `sequence` is a JSON integer
starting at 1. A present anchor timestamp is the parsed `HistoricalBar`
timestamp converted to `Asia/Taipei` and serialized exactly as
`YYYY-MM-DDTHH:MM:SS+08:00`, without fractional seconds. Its bar digest is
SHA-256 over the exact canonical source JSON object bytes from the immutable
Dataset `bars.jsonl`, excluding the one terminating JSONL LF. The source bytes
must parse as one `HistoricalBar`, and canonical reserialization of that bar
must equal those bytes exactly; hashing the parsed object, a reduced projection,
or bytes including LF is prohibited. The same source bytes plus exactly one LF
remain part of the Dataset payload SHA. Timestamp/digest pairs are both present
or both JSON null. `eligibility_status` is `ELIGIBLE` or `EXCLUDED`. Eligible
rows require both anchors and an empty reason array; excluded rows require the
exact missing-anchor reasons. The self-digest omits only
`eligibility_row_digest`.

The eligibility manifest exact keys are:

```text
schema_version, dataset_id, dataset_digest, dataset_bars_sha256,
common_signal_cutoff_time, entry_fill_deadline_time,
required_terminal_exit_time, eligibility_row_schema_version,
observed_symbol_session_count, eligible_symbol_session_count,
excluded_symbol_session_count, missing_entry_reserve_count,
missing_terminal_exit_count, eligible_symbol_session_ratio,
minimum_eligible_symbol_session_ratio, eligibility_rows_sha256,
eligibility_manifest_digest
```

`schema_version=r6-session-eligibility-manifest-v1`. Row SHA is over exact
canonical JSONL bytes. All counts, ratio, anchor lineage, and Dataset roots are
recomputed on every read. Unknown/missing fields, count drift, digest drift,
or a different common mask fail closed.

Every slot's ledger, match, result, and postflight manifest adds the exact
field `eligibility_manifest_digest`; their schema literals advance to
`r6-ledger-manifest-v2`, `r6-match-manifest-v2`,
`r6-result-manifest-v2`, and `r6-postflight-v2`. Postflight diagnostics also
add:

```text
observed_symbol_session_count, eligible_symbol_session_count,
excluded_symbol_session_count, missing_entry_reserve_count,
missing_terminal_exit_count, eligible_symbol_session_ratio
```

Postflight acceptance adds the exact boolean
`common_session_eligibility_verified`. It must participate in
`all_conditions_accepted`. `missing_entry_count` and `missing_exit_count` for
eligible sessions must still both equal zero; an implementation may not relabel
an admitted incomplete signal as Dataset exclusion.

The G3 root member paths are exactly:

```text
preflight_manifest.json
eligibility/rows.jsonl
eligibility/manifest.json
slot-01/ledger.jsonl
slot-01/matches.jsonl
slot-01/ledger_manifest.json
slot-01/match_manifest.json
slot-02/ledger.jsonl
slot-02/matches.jsonl
slot-02/ledger_manifest.json
slot-02/match_manifest.json
slot-03/ledger.jsonl
slot-03/matches.jsonl
slot-03/ledger_manifest.json
slot-03/match_manifest.json
slot-04/ledger.jsonl
slot-04/matches.jsonl
slot-04/ledger_manifest.json
slot-04/match_manifest.json
slot-05/ledger.jsonl
slot-05/matches.jsonl
slot-05/ledger_manifest.json
slot-05/match_manifest.json
slot-06/ledger.jsonl
slot-06/matches.jsonl
slot-06/ledger_manifest.json
slot-06/match_manifest.json
slot-07/ledger.jsonl
slot-07/matches.jsonl
slot-07/ledger_manifest.json
slot-07/match_manifest.json
```

There are exactly 31 files: the top-level manifest, two eligibility members,
and four members for each ordered slot `01..07`. Missing, additional, renamed,
symlinked, non-regular, or differently cased members fail closed. Directory and
filesystem enumeration order is never identity.

The top-level preflight manifest exact keys are:

```text
schema_version, family_id, matrix_id, matrix_revision, registration_digest,
research_baseline_digest, dataset_id, dataset_digest, dataset_bars_sha256,
dataset_bar_count, dataset_binding_revision, source_bar_count,
source_bars_sha256, source_eof_verified, protocol_core_digest,
algorithm_contract_digest, algorithm_implementation_digest,
preflight_implementation_digest, eligibility_manifest_digest, slots,
preflight_digest
```

Its literal is `schema_version=r6-preflight-manifest-v2` and
`matrix_revision=2`. `slots` contains exactly seven rows ordered by
`slot_sequence`; every row has exact keys:

```text
schema_version, slot_sequence, hypothesis_id, eligibility_manifest_digest,
ledger_manifest_digest, match_manifest_digest, signal_count, matched_count
```

The slot-root literal is `schema_version=r6-preflight-slot-root-v2`. Every slot
root repeats the same eligibility manifest digest. `preflight_digest` is the
self-digest of the exact top-level object with only `preflight_digest` omitted.
The top-level verifier must reload all 31 exact members, canonical bytes, row
streams, manifests, counts, multiplicity projections, Dataset roots, eligibility
root, seven ordered slot roots, and implementation roots before accepting it.

Publication remains all-or-none and contains no episode, price outcome, cost,
metric, result summary, rank, or disposition. It first atomically renames the
fully verified digest-addressed artifact root, then separately registers that
already-published root in PostgreSQL under Section 14.5. A crash between those
steps may leave an unregistered immutable root, but never an accepted preflight;
same-input retry must verify and reuse that byte-identical root.

### 14.4 Current identity projections

The exact `protocol_core` key set is the Section 3.5 set plus:

```text
common_signal_cutoff_time, common_signal_cutoff_comparator,
entry_fill_deadline_time, entry_fill_deadline_comparator,
required_terminal_exit_time, session_eligibility_semantics,
incomplete_signal_semantics, eligibility_scope,
minimum_eligible_symbol_session_ratio, eligibility_ratio_scale,
eligibility_ratio_comparator
```

The changed literals are:

```text
schema_version = r6-protocol-core-v2
signal_admission = FIRST_TRIGGER_PER_SLOT_SYMBOL_ELIGIBLE_SESSION_BEFORE_COMMON_CUTOFF_V2
entry_semantics = NEXT_OBSERVED_SAME_SYMBOL_SAME_SESSION_KBAR_OPEN_STRICTLY_AFTER_SIGNAL_AND_NOT_AFTER_COMMON_ENTRY_DEADLINE_V2
exit_semantics = EXACT_SAME_SYMBOL_SAME_SESSION_13_30_KBAR_CLOSE_STRICTLY_AFTER_ENTRY_V2
session_eligibility_semantics = REQUIRE_EXACT_12_45_ENTRY_RESERVE_AND_13_30_TERMINAL_BAR_V1
incomplete_signal_semantics = EXCLUDE_INELIGIBLE_SYMBOL_SESSION_BEFORE_ALL_SLOT_ADMISSION_V1
eligibility_scope = COMMON_SYMBOL_SESSION_MASK_SHARED_BY_ALL_SEVEN_SLOTS_V1
minimum_eligible_symbol_session_ratio = 0.95
eligibility_ratio_scale = 18
eligibility_ratio_comparator = GTE
```

Every other protocol value remains exactly as in Section 3.5. The frozen
Amendment A1 `protocol_core_digest` is:

```text
a4d645b5ea59fca5a90a00c9e14ca117366d87e4f310b88354fc73d03272f471
```

The exact amended `hypothesis_spec_digest`, `version_binding_digest`,
`hypothesis_id`, and `slot_digest` values are:

| Slot | Hypothesis spec | Version binding | Hypothesis ID | Slot digest |
|---:|---|---|---|---|
| 1 | `2a5f55b98acc6ed066bedfad66525c5c04b6312e374fd32b9d44bd00ee9682e2` | `236e29f3bcbcb8b0c4f6a7074381b49e877b4b059b920996688a4cbb612e1897` | `8655be638a4f430147fc62cd3b03b2d50a2d15ff05c4bcc83442001eb31a69bb` | `8deab12b0aac8f79063712f7b96c9f6cf715baaa3f6dcdf26d171c4462faf86a` |
| 2 | `2659227c74c384f7c5516c7755cb5f54b96db07b9b16b5f3cd0a14a39ddd9b6e` | `f3065cd186c2ad442f3660894266ee306f01187d9aee4ae48431a4731654b02f` | `9f740fdd8280a5c1bd3ef085d6681bf829fe107bf38cd07ba5b64cd3c13fd3e0` | `34a1c40eadf50d15d01fdefbe47576598599640117eb5274c750ac92e84e5a8f` |
| 3 | `f19f183392093fe598a28beef08964354bca88600325fb32639ab0dfda1a760e` | `f6c1c7d337d3800d99b58819cffaec4159e111d4c112db415c70350e1376f9bc` | `caae4710b861dadf75c1b774f0894bb000102cec25e65715548e96429caddb56` | `025bb8ea052778bdf4e2319d03bed3462dbe28cc6e5be7518bcf088dd3c5dd7c` |
| 4 | `b6480d5e63adbdcfc8ce0e42b235414bd7dfc0076ecf06be22cde58a1bcc17c9` | `d24d5ab1cf16249e754eeebfaf519967b0f8ecc6594bf8a951be384b71afeaa8` | `0aba8ad67219002e4031538248f50c2f7ae64080ca9936c911ee2b113e84cf90` | `263ba9b2b9ef7cddcadacea42a2b52cd3614a6f0f0362f7f15679317f4bd27bf` |
| 5 | `fc753e5b692552389c55a01a71926d04b32ff5c0ab23e0ddb70a277277e2111a` | `bfb5a5033901ad0be9ce973ebf0c446dd780ac9a9f62adf6e4d6a7da920a9c62` | `78220b84a04fdea0699c00b171a773b5e7efc963acddc1b5d870a47f51f7ca7e` | `b88590c1c02e1bcb2522f1c9e5fda82e76c3934c841c98df3528a6a96636a003` |
| 6 | `d1c4b77a0d9e09eba0162615cb171236c05c603bf649662be37981d11cea5791` | `332300f72d2a4f99e7898670cc8d2ab07a5a4f60e24531820d9f31b09e1b2237` | `d8b4b691b515c315e0e6e1bbb27b6856248fdcec46e4f30bfff95c5f0e4a4b0c` | `0a2350ccb0b2a516f72b944b10cfc9be9556f0ce93682cadfa7e861387543d61` |
| 7 | `3c61fc9fdc1f86043fee1289d81c88d6458071fb5925ccbcaa53a2d4f8fbb7d2` | `5e71bf74e62de220ba629293ff7bfbde854e0cc6d4fc55a390926ee8d9da92b0` | `57ec8b01a7e5272425dde3f72d68c7baf716c6b4f8e74ef1c74e25efffe52c29` | `723d1708f4627d0cf2759a2842401ae55cc8575bf79651a0e73eaab974996716` |

No Strategy Version, lifecycle event, or attempt is recreated. These R6-only
bindings change because the protocol digest changes.

The amended algorithm contract is the exact canonical object:

```json
{"calculation_precision":38,"calculation_rounding":"ROUND_HALF_EVEN","canonical_json":"BACKTEST_CANONICAL_JSON_V1","common_signal_cutoff_comparator":"STRICT_LT","common_signal_cutoff_time":"12:45","contract_version":"r6-atomic-entry-benchmark-v2","eligibility_ratio_comparator":"GTE","eligibility_ratio_scale":18,"entry_fill_deadline_comparator":"LTE","entry_fill_deadline_time":"12:45","entry_semantics":"NEXT_OBSERVED_SAME_SYMBOL_SAME_SESSION_KBAR_OPEN_STRICTLY_AFTER_SIGNAL_AND_NOT_AFTER_COMMON_ENTRY_DEADLINE_V2","exit_semantics":"EXACT_SAME_SYMBOL_SAME_SESSION_13_30_KBAR_CLOSE_STRICTLY_AFTER_ENTRY_V2","incomplete_signal_semantics":"EXCLUDE_INELIGIBLE_SYMBOL_SESSION_BEFORE_ALL_SLOT_ADMISSION_V1","minimum_eligible_symbol_session_ratio":"0.95","name":"independent-one-lot-atomic-entry-zero-edge-v2","required_terminal_exit_time":"13:30","return_scale":18,"session_eligibility_semantics":"REQUIRE_EXACT_12_45_ENTRY_RESERVE_AND_13_30_TERMINAL_BAR_V1","shares_semantics":"EXACT_ONE_LOT_1000_SHARES_V1","signal_admission":"FIRST_TRIGGER_PER_SLOT_SYMBOL_ELIGIBLE_SESSION_BEFORE_COMMON_CUTOFF_V2","timezone":"Asia/Taipei"}
```

Its frozen `algorithm_contract_digest` is:

```text
d0d3b66395a06f600c698bad7890ad39f2dceec2963727814e5d3198643df0b6
```

The Amendment A1 `benchmark_build_binding` advances to the exact keys:

```text
schema_version, protocol_core_digest, algorithm_contract_digest,
algorithm_implementation_digest, preflight_implementation_digest,
persistence_schema_digest
```

Its literal is `schema_version=r6-benchmark-build-binding-v2`. The algorithm
implementation digest retains the Section 3.5 algorithm source-manifest
projection and exact six-file order, using the post-A1 reviewed bytes. The
preflight implementation digest is SHA-256 over the canonical object with exact
keys `schema_version, files`, literal
`schema_version=r6-preflight-source-manifest-v2`, and these exact ordered rows:

```text
backtest/atomic_benchmark/preflight.py
backtest/atomic_strategy_adapter.py
scripts/preflight_atomic_entry_benchmark.py
```

Each row has exact keys `path`, `byte_count`, `sha256`; paths are the exact
repository-relative ASCII strings above, counts are JSON integers, and SHA
values are lowercase hex. The persistence digest uses the same exact manifest
and row schemas with literal
`schema_version=r6-persistence-source-manifest-v2` and exact ordered paths:

```text
backtest/migrations/016_atomic_entry_benchmark.sql
backtest/migrations/017_r6_matrix_revision_and_preflight.sql
```

No concatenation, filesystem enumeration order, locator, mtime, or parsed SQL
projection may replace these canonical manifests. Matrix activation rebuilds
all three source manifests from reviewed repository bytes. G3 publication and
PostgreSQL preflight registration must prove their
`preflight_implementation_digest` equals the value already sealed in this
matrix build binding; a self-declared runtime digest is not authority.

### 14.5 Matrix revision, durable preflight, and migration contract

The stable family and its 20-attempt budget are preserved. Matrix revision 1
remains immutable and inactive for future execution. After this frozen A1
contract receives separate implementation authorization, a forward-only
Migration 017 must execute in one transaction. Before reading any mutable
precondition it locks the exact family row with `SELECT ... FOR UPDATE`; every
attempt start, matrix activation, and preflight-registration mutation must acquire
that same family row lock before changing family-owned state. While holding the
lock, Migration 017 verifies the head/attempt/revision-1 preconditions before
its first schema-altering or data-mutating statement. The lock is held through
DDL validation and commit; any failure rolls back the entire migration without
schema or row changes. It must:

1. prepare support for matrix revision `2` without any `UPDATE` or `DELETE` of
   existing revision-1 matrix, slot, release, operation, outbox, family, or root
   rows. Migration 017 itself does not activate revision 2 and does not update
   the family row. The separately invoked activation transaction is the sole
   exception: after rebuilding all preconditions under the family lock, it may
   CAS only `active_matrix_revision` from `1` to `2` and advance `updated_at`;
   every other pre-existing family column must remain byte-equivalent;
2. remove the `UNIQUE(family_id, slot_sequence)` restriction that prevents a
   second immutable matrix while preserving `PRIMARY KEY(matrix_id,
   slot_sequence)` and `UNIQUE(family_id, matrix_revision)`;
3. preserve every existing operation, outbox, slot, and revision-1 root;
4. allow activation of revision 2 only with family head `0`, attempt count `0`,
   expected active revision `1`, and an exact CAS;
5. make same-key/same-digest replay a no-op and reject stale revision,
   different digest, any consumed attempt, or a third matrix;
6. create the additive companion table
   `atomic_entry_benchmark_matrix_protocols`; do not add or backfill protocol
   columns on existing matrix rows. Its exact authoritative columns are
   `matrix_id` primary key, `family_id`, `matrix_revision`,
   `protocol_core_json`, and `protocol_core_digest`. It has unique
   `(family_id, matrix_revision)`, unique
   `(matrix_id, family_id, matrix_revision)`, a composite foreign key to the
   same matrix triple, and a canonical lowercase SHA-256 constraint. After the
   matrix composite key and companion table exist in that same migration
   transaction, Migration 017 rebuilds the revision-1 family protocol, verifies
   its canonical JSON bytes and digest against the revision-1 matrix
   registration, and inserts one new immutable revision-1 companion row. This
   is an additive projection, not a mutation of the revision-1 matrix or family
   row. Revision 2 inserts its Amendment A1 protocol companion row in the matrix
   activation transaction. The family protocol columns remain immutable
   revision-1 inception evidence and are never overwritten. Every
   post-Migration-017 matrix protocol read resolves through the companion row
   for the selected exact matrix revision; a missing, duplicate, mismatched, or
   digest-drifted companion row fails closed;
7. add both `UNIQUE (matrix_id, family_id)` and
   `UNIQUE (matrix_id, family_id, matrix_revision)` to matrices. The two-column
   key is the exact referenced unique target for operation, outbox, and slot
   `(matrix_id, family_id)` foreign keys; the three-column key is the exact
   referenced unique target for protocol, release, and preflight
   `(matrix_id, family_id, matrix_revision)` foreign keys. A foreign key must
   not rely on the single-column `matrix_id` primary key to imply uniqueness of
   either composite identity. Existing independent foreign keys are retained
   only when they do not weaken these composite constraints;
8. replace the matrix and release revision-1-only checks with exact
   `matrix_revision IN (1, 2)` checks, require family
   `active_matrix_revision` to be non-null and in `(1, 2)`, and reject every
   revision outside that set at the database boundary. Migration 017 verifies
   the existing active revision is exactly `1` before changing these schema
   constraints; no application-only guard may stand in for them;
9. verify every existing operation and outbox row has a non-null `matrix_id`
   whose `(matrix_id, family_id)` pair is valid, then make both columns
   `NOT NULL` and add the exact pair foreign keys. Add
   `UNIQUE (operation_id, family_id, matrix_id)` to operations and make outbox
   reference that exact operation aggregate, not only an independent
   `operation_id`;
10. replace the removed slot uniqueness with
   `UNIQUE (matrix_id, family_id, slot_sequence, hypothesis_id)` and add the
   corresponding composite attempt foreign key. A revision-2 attempt bound to a
   revision-1 hypothesis, a different slot, or another family must fail at the
   database boundary. Also add
   `UNIQUE (attempt_id, family_id, matrix_id)` to attempts; transition evidence
   must reference that exact attempt aggregate. Attempt-bound operation and
   outbox rows use the same composite attempt foreign key; a null `attempt_id`
   is permitted only for the frozen matrix-level operation types and never
   weakens their non-null matrix/family relationship;
11. permit release revision `2`, create exactly one revision-2 `NOT_READY`
   release with the matrix activation transaction, and preserve the immutable
   revision-1 release;
12. add the exact durable G3 registration described below and make attempt
   `preflight_id` non-null with a composite `(preflight_id, matrix_id)` foreign
   key backed by `UNIQUE (preflight_id, matrix_id)`. Migration must first prove
   head `0`, attempt count `0`, and no non-null revision-1 execution evidence;
   otherwise it aborts without schema mutation.

Revision-2 matrix activation is a distinct `ACTIVATE_MATRIX_REVISION_2`
operation. Its request has exact keys:

```text
schema_version, expected_active_matrix_revision,
expected_family_head_sequence, expected_attempt_count, research_baseline,
protocol_core, benchmark_build_binding, slots, actor_id, change_note
```

The literal is `schema_version=r6-matrix-activate-request-v2`; expected active
revision is `1`, expected head and attempt count are `0`, and the nested bodies
are the exact A1 projections. The result has exact keys:

```text
schema_version, family_id, matrix_id, matrix_revision, registration_digest,
previous_active_matrix_revision, active_matrix_revision,
family_head_sequence, attempt_count, status
```

Its literals are `schema_version=r6-matrix-activate-result-v2`, matrix/active
revision `2`, previous revision `1`, both counts `0`, and `status=SEALED`. The
single transaction locks the family, fully rebuilds revision 1 including its
companion protocol projection, verifies the source Run and complete G1 Version
publication graph, inserts the revision-2 matrix, protocol companion row, seven
slots and `NOT_READY` release, performs the family active-revision CAS, then
inserts the immutable operation and `MATRIX_REVISION_ACTIVATED` outbox.
The CAS is exactly `UPDATE ... SET active_matrix_revision=2,
updated_at=CURRENT_TIMESTAMP WHERE family_id=:family_id AND
active_matrix_revision=1 AND head_sequence=0`; its affected-row count must be
exactly one. A canonical before/after family projection must prove that only
`active_matrix_revision` and the operational `updated_at` changed; any drift in
source lineage, research baseline, protocol inception evidence, planned-attempt
policy, head sequence, release state, actor, or creation time rolls back the
transaction.
Same-key/same-digest replays that exact result; same-key/different-digest,
different-key after activation, stale active revision, any existing attempt,
or a pre-existing third matrix fails closed without a second operation/outbox.

The canonical matrix core/registration key sets remain unchanged with
`matrix_revision=2`; both reference the matrix-owned Amendment A1 protocol
digest and the digest of the v2 build binding above. Their final digests cannot
be frozen until the reviewed algorithm/preflight source manifests and exact
Migration 016+017 persistence manifest are available. Silently reusing the
revision-1 build binding or accepting a preflight digest that is not sealed in
the v2 binding is prohibited.

Migration 017 adds `atomic_entry_benchmark_preflights`. Its authoritative
columns are `preflight_id` primary key, exact matrix/family/revision identity,
`preflight_json`, `preflight_digest`, `eligibility_manifest_digest`,
`preflight_registration_json`, `preflight_registration_digest`, `status`, and
the unique creating `operation_id`. `preflight_json` is the exact verified
top-level v2 manifest; no reduced projection is saved. `artifact_locator`,
actor/change note, and audit
timestamps are operational audit columns and never participate in immutable
identity. Constraints require `matrix_revision=2`, `status=ACCEPTED`, unique
`matrix_id`, unique `(family_id, matrix_revision)`, unique `preflight_digest`,
unique `preflight_registration_digest`, canonical lowercase SHA-256 values, and
the composite matrix foreign key above.

`preflight_id` is exactly `r6-preflight-sha256-<preflight_digest>`. The canonical
preflight-registration body has exact keys:

```text
schema_version, preflight_id, family_id, matrix_id, matrix_revision,
matrix_registration_digest, protocol_core_digest, dataset_id, dataset_digest,
dataset_bars_sha256, dataset_binding_revision, eligibility_manifest_digest,
preflight_digest, preflight_implementation_digest, status
```

Its literals are `schema_version=r6-preflight-registration-v1`,
`matrix_revision=2`, and `status=ACCEPTED`; its canonical digest is
`preflight_registration_digest`. Its `preflight_implementation_digest` must
equal the exact v2 matrix build-binding field and is rebuilt from repository
bytes again during registration and every G4 admission read.

The registration use case accepts a stable idempotency key and a preflight root
that has already passed the complete 31-member verifier. Its canonical request
has exact keys:

```text
schema_version, family_id, matrix_id, matrix_revision,
expected_active_matrix_revision, expected_family_head_sequence,
expected_attempt_count, preflight_id, preflight_digest,
eligibility_manifest_digest, preflight_registration_digest,
actor_id, change_note
```

Literals are `schema_version=r6-preflight-register-request-v1`, both revisions
`2`, expected head/attempt count `0`. One PostgreSQL transaction takes the family
advisory and row locks, rebuilds the active matrix and registration, rechecks
head/attempt zero, verifies the exact preflight registration projection, then
inserts the preflight registration, immutable operation result, and outbox. The
result exact keys are:

```text
schema_version, family_id, matrix_id, matrix_revision, preflight_id,
preflight_digest, eligibility_manifest_digest,
preflight_registration_digest, status, family_head_sequence, attempt_count
```

Its literals are `schema_version=r6-preflight-register-result-v1`,
`matrix_revision=2`, `status=ACCEPTED`, and both counts `0`. Same key and request
digest replays this exact result after rebuilding operation, registration, and
outbox evidence. Same key/different digest conflicts. A different key after an
accepted registration returns `R6_PREFLIGHT_ALREADY_ACCEPTED` and creates no
second operation or outbox. Missing artifact bytes, locator substitution without
identical verified bytes, root/registration drift, stale matrix, or response-loss
result substitution fails closed.

The operation literal is `REGISTER_PREFLIGHT_V2`; the outbox topic is
`ATOMIC_ENTRY_BENCHMARK_PREFLIGHT_ACCEPTED`. Exact failure mapping is:

| Condition | Error code |
|---|---|
| Same key, different request digest | `R6_IDEMPOTENCY_CONFLICT` |
| Different key after one accepted registration | `R6_PREFLIGHT_ALREADY_ACCEPTED` |
| Missing/non-canonical/member/digest/registration/operation/outbox evidence | `R6_PREFLIGHT_INTEGRITY_ERROR` |
| Matrix ID/revision/active-revision mismatch | `R6_MATRIX_IDENTITY_CONFLICT` |
| Family head is not zero | `R6_FAMILY_HEAD_SEQUENCE_CONFLICT` |
| Any attempt already exists | `R6_PREFLIGHT_ATTEMPT_COUNT_CONFLICT` |
| Attempt start lacks the exact accepted preflight | `R6_PREFLIGHT_NOT_ACCEPTED` |

G4 attempt admission is impossible before this registration. The exact attempt
start request adds `expected_preflight_id` and
`expected_preflight_registration_digest`. Under the existing family-head lock,
the repository must rebuild the active revision-2 matrix and accepted preflight,
verify both expected values and all matrix/protocol/Dataset/eligibility roots,
and store that exact `preflight_id` on the new attempt. Revision 1, a missing or
non-accepted preflight, a preflight from another matrix/revision, and any
filesystem locator supplied directly by a caller fail closed. Application and
CLI layers may access this aggregate only through the repository port; filesystem
existence is never admission authority.

### 14.6 Required regressions and Gate state

The frozen implementation acceptance matrix requires at least:

- signal at `12:44`, exact `12:45` entry, exact `13:30` exit: complete;
- event at exactly `12:45`: strategy blocked, no signal;
- missing `12:45`, missing `13:30`, and both missing: common exclusion with
  exact reason codes across all seven slots;
- duplicate anchor, entry after `12:45`, exit not exactly `13:30`, same-bar
  entry/exit, cross-session carry, and synthetic anchor: fail closed;
- a strategy-specific attempt to retain/exclude a different symbol/session
  mask: fail closed;
- eligible-ratio values immediately below, equal to, and above `0.95`, using
  18-place `ROUND_HALF_EVEN` before comparison;
- mask/row/count/reason/digest substitution and canonical-byte tamper;
- anchor digest computed from bytes with LF, parsed/reformatted JSON, a reduced
  bar projection, or a timestamp with a different offset/precision: fail closed;
- bounded one-session spool, clean interruption, response-loss replay, and
  byte-identical clean-root rebuild;
- algorithm/preflight/persistence source-manifest missing, extra, reordered,
  path, byte-count, SHA, schema, or runtime-self-declared digest substitution;
  all fail before matrix activation or preflight acceptance;
- excluded sessions still affect source count/SHA/order and the source-only
  previous-close map but never strategy/Feature state or signal admission;
- exact 31-member root schema/path/order verification, missing/extra/symlink
  members, slot/eligibility/root substitution, and unregistered-orphan reuse;
- preflight register same-key replay, different-key rejection, operation/outbox
  tamper, root/locator substitution, and PostgreSQL transaction rollback;
- matrix revision-2 CAS/concurrency/tamper tests with head and attempts still
  zero;
- Migration 017 alone leaves the complete family row unchanged; revision-2
  activation changes only `active_matrix_revision: 1 -> 2` and operational
  `updated_at`, with affected-row count one and byte-equivalent before/after
  evidence for every other family column;
- a concurrent revision-1 attempt start before Migration 017 obtains the family
  lock makes migration preflight fail; one arriving after the migration lock
  waits and then fails against the superseded revision/preflight admission
  contract. No interleaving may both pass head/attempt zero;
- Migration-017 before/after projections prove every pre-existing revision-1
  row is byte-equivalent, while exactly one new verified revision-1 protocol
  companion exists; family/registration protocol mismatch, missing companion,
  companion digest tamper, and cross-revision substitution roll back or fail
  closed;
- cross-revision matrix/protocol/hypothesis/slot/family attempt substitutions
  rejected by composite foreign keys; revision-1 matrix/family/release rows
  remain unchanged while their additive protocol companion stays immutable;
- PostgreSQL catalog acceptance proves matrices own both exact unique keys,
  `(matrix_id, family_id)` and `(matrix_id, family_id, matrix_revision)`;
  operation, outbox, and slot inserts that substitute another family for a
  valid matrix fail at their two-column foreign-key boundary, while protocol,
  release, and preflight cross-revision substitutions fail at their
  three-column boundary;
- catalog acceptance proves matrix/release/family active revisions allow only
  `1` or `2`; direct revision `0`, `3`, or null insertion/update fails closed;
- operations and outbox reject null or cross-family matrix identity; outbox
  cannot substitute an operation from another matrix/family, and transition
  evidence plus every attempt-bound operation/outbox row cannot substitute an
  attempt from another matrix/family;
- attempt start without the exact accepted revision-2 preflight, or with a
  different expected preflight registration digest, fails before head mutation;
- proof that no Version/lifecycle mutation, attempt consumption, metric,
  provider, broker, Local Paper, or real-money path occurs.

Current disposition:

```text
R6 revision 2 historical G0/G1/G2: PASSED
G0 Amendment A1: PASSED / CONTRACT FROZEN
Matrix revision 1: SEALED / ZERO ATTEMPTS / NOT EXECUTABLE FOR G3
Matrix revision 2: NOT CREATED
Migration 017 / matrix revision 2: NOT STARTED / REQUIRES SEPARATE AUTHORIZATION
G3: BLOCKED ON A1 IMPLEMENTATION
G4-G5: NOT AUTHORIZED
Formal Replay: 0 / 7
Local Paper / Broker / Real-money: PROHIBITED
```
